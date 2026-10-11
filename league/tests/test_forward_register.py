"""Release E3, the forward registry's job (league/ops/forward_register.py): every equity version judged on the Train
bar is registered, passed or failed, and one that could not be judged is not; seeds and live instances; what is
refused, with its event written once over many runs; T6 `RetroOnlyWithAnEvent` (no registry row claims a time before
its evidence: a window that opens before the registry first saw the program needs the swarm's scored event for that
very code); the controls arriving with a group's first program; the tags; THE STOP RULES (the session cap on stored
days, three disqualified nights, three failed nights give suspect and never a stop, a House failure gives nothing, a
resume makes old nights count no more); a second run adding nothing; the event cursor; whose failure an unreadable
store is; the identity watch; and the job's receipt and alerts. The swarm store is the real one on a temporary
directory; every family, program, verdict, day and number is invented, and no market data is read."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import config, results, schedule
from league.ops import forward_controls as C
from league.ops import forward_db as F
from league.ops import forward_register as R
from league.ops.context import Context
from league.swarm import elane, elane_train
from league.swarm.gate import run_sha
from league.swarm.store import SwarmStore
from league.tests import elane_e2_fakes as fx
from league.tests.test_forward_db import at, sessions_from, sha

UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD"]
#: Invented Train verdicts as E2's record keeps them (league/swarm/elane_train.py `compact`, `program_fault`).
PASSED = {"passed": True, "fails": [], "pnl_10": 180.0, "pnl_15": 120.0}
FAILED = {"passed": False, "fails": ["P1"], "pnl_10": 30.0, "pnl_15": -2.0}
STATE = {"passed": False, "fails": ["STATE"], "pnl_10": 50.0, "pnl_15": 40.0}
REVIEW = {"passed": False, "bar_passed": True, "fails": ["REVIEW"], "pnl_10": 100.0, "pnl_15": 70.0}
UNJUDGED = {code: elane_train.program_fault(code, "an invented fault") for code in ("RUN", "DQ", "LOAD")}
UNJUDGED["WINDOW"] = {"passed": False, "fails": ["WINDOW"], "pnl_10": None, "pnl_15": None}
#: A text an alert may hold: ids, counts and dates only (the spec's T8): no decimal figure, no "bp", "%" or "$".
FIGURE = re.compile(r"\d\.\d|\bbp\b|%|\$")


class Clock:
    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t


class House:
    """A House state root: the real swarm store, the forward store, and (once `book` is called) a live book."""

    def __init__(self, case: unittest.TestCase, *, now: float | None = None, **forward):
        tmp = tempfile.TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.days = sessions_from(F.t0(), 60)
        self.clock = Clock(at(self.days[2], 10) if now is None else now)
        self.swarm = SwarmStore(self.root, clock=self.clock)
        case.addCleanup(self.swarm.close)
        self.db = F.open_db(self.root)
        case.addCleanup(self.db.close)
        self.settings = {"elane": {"mode": "gate", "universe": list(UNIVERSE),
                                   "forward": {"mode": "record", "controls_per_group": 3, **forward}}}

    def family(self, slug: str, verdicts: dict | None = None, *, lane: str = "equity", symbols=("QQQ",),
               agenda: str = "trend", codes: int = 1, params: dict | None = None, **record) -> str:
        fam = fx.e2_family(self.swarm, slug, lane=lane, agenda=agenda, symbols=tuple(symbols))
        for n in range(1, codes + 1):
            self.swarm.add_version(fam["id"], fx.program(symbols[0], share=n / 10), params or {}, author="fake:author")
        versions = {str(n): dict(v) for n, v in ({1: FAILED} if verdicts is None else verdicts).items()}
        self.swarm.set_state(fam["id"], **{elane_train.STATE_KEY: {"status": "researching", "versions": versions,
                                                                 **record}})
        return str(fam["id"])

    def scored(self, fid: str, n: int = 1, *, bar_passed: bool = False, code_sha: str | None = None,
               when: float | None = None, **payload) -> int:
        """The swarm's scored event for a version (E3's patch of `EquityResearcher.score`), at `when`."""
        if when is not None:
            self.clock.t = when
        code_sha = self.swarm.version(fid, n)["sha"] if code_sha is None else code_sha
        return self.swarm.event("swarm.elane", fid, {"pass": "scored", "version": n, "sha": code_sha,
                                                     "bar_passed": bar_passed, "fails": [], "objective": "equity-v1",
                                                     "judged": True, **payload})

    def sync(self, when: float | None = None) -> dict:
        if when is not None:
            self.clock.t = when
        return R.sync(self.root, self.db, now=self.clock(), settings=self.settings)

    def row(self, key: str) -> dict | None:
        found = self.db.execute("SELECT * FROM fwd_registry WHERE key=?", (key,)).fetchone()
        return None if found is None else dict(found)

    def keys(self, where: str = "reason != 'control'") -> list[str]:
        return [r["key"] for r in self.db.execute(f"SELECT key FROM fwd_registry WHERE {where} ORDER BY pid")]

    def book(self, *instances: dict) -> None:
        """A live book holding these equity instances (league/equity/live.py's own tables)."""
        from league.equity import live

        db = sqlite3.connect(str(self.root / R.LIVE_DB))
        try:
            db.executescript(live.SCHEMA)
            for row in instances:
                held = {"lane": "beta", "band": "probe", "seeded": 0, "max_hold": 2, "created_at": self.clock(),
                        "retired_at": None, **row, "params": json.dumps(row.get("params") or {})}
                db.execute(f"INSERT OR REPLACE INTO eq_instances({', '.join(held)}) VALUES({', '.join('?' * len(held))})",
                           list(held.values()))
            db.commit()
        finally:
            db.close()

    def instance(self, fid: str, n: int = 1, **over) -> dict:
        version = self.swarm.version(fid, n)
        return {"id": f"{fid}@{n}:r", "family": fid, "version": n, "run_sha": run_sha(version),
                "code": version["code"], "params": version["params"], **over}

    # ------------------------------------------------------------------ what the shadow writes (invented rows)
    def engine(self, label: str = "an-invented-engine") -> int:
        return F.engine_id(self.db, label, at=self.clock())[0]

    def stored(self, pid: int, n: int, *, engine: int, first: int = 0, status: str = "ok", written: float | None = None):
        for day in self.days[first:first + n]:
            self.db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at) VALUES(?, ?, ?, "
                            "0.0, 0.0, 0.0, 0, 0, ?, ?)", (pid, day.isoformat(), engine, status,
                                                           self.clock() if written is None else written))
        self.db.commit()

    def night(self, index: int, *, programs: int = 1, marks: dict | None = None, ran: dict | None = None) -> str:
        """One shadow night named by session `index`: its `fwd_runs` row and each pid's event of that night, as the
        shadow writes them (league/ops/forward_shadow.py: `day` the night, `once` the word "night"). `ran`: {pid: the
        status of the run of it that completed that night}: its rows from its last stored day through the night's,
        written by that night (the whole recompute fills the days earlier nights left it stale on)."""
        through = self.days[index].isoformat()
        self.clock.t = at(self.days[index], 19)
        for pid, status in (ran or {}).items():
            last = self.db.execute("SELECT MAX(day) FROM fwd_days WHERE pid=?", (pid,)).fetchone()[0]
            first = 0 if last is None else [d.isoformat() for d in self.days].index(last) + 1
            self.stored(pid, index + 1 - first, engine=self.engine(), first=first, status=status, written=self.clock() - 30)
        self.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs) VALUES("
                        "'forward_shadow', ?, 1, ?, ?, 1.0, ?)", (through, self.clock() - 60, self.clock(), programs))
        self.db.commit()
        for pid, kind in (marks or {}).items():
            F.event(self.db, kind, pid=pid, day=through, payload={"why": "an invented night"}, at=self.clock(),
                    once="night")
        return through


class Registered(unittest.TestCase):
    def test_every_version_judged_on_the_bar_passed_or_failed(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED, 2: FAILED, 3: STATE, 4: REVIEW}, codes=4, passed_version=1)
        out = h.sync()
        self.assertEqual((out["registered"], out["skipped"]), (4, []))
        self.assertEqual(h.keys(), [f"{fid}@1", f"{fid}@2", f"{fid}@3", f"{fid}@4"])
        self.assertEqual([h.row(k)["reason"] for k in h.keys()], ["train_pass", "train_fail", "train_fail", "train_pass"],
                         "a STATE failure was judged on the bar; one the review refused passed the bar")
        self.assertTrue(out["chain"]["ok"])
        self.assertEqual(out["chain"]["rows"], 4 + 3)   # with its group's three controls

    def test_a_version_that_could_not_be_judged_is_not(self):
        h = House(self)
        verdicts = {i + 1: v for i, v in enumerate(UNJUDGED.values())}
        fid = h.family("alpha", {**verdicts, 5: FAILED}, codes=5)
        h.family("beta", {1: UNJUDGED["RUN"]})
        h.family("gamma", {})                       # a family with no version scored yet
        out = h.sync()
        self.assertEqual(h.keys(), [f"{fid}@5"])
        self.assertEqual((out["registered"], out["skipped"]), (1, []), "unjudged is not refused: it has no figure")
        self.assertEqual(F.events(h.db, "register_skipped"), [])

    def test_the_rows_columns(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED}, lane="beta", symbols=("SPY",), params={"share": 0.25})
        now = h.clock()
        h.sync()
        row, version = h.row(f"{fid}@1"), h.swarm.version(fid, 1)
        self.assertEqual({k: row[k] for k in ("pid", "family", "version", "lane", "reason", "ugroup", "lineage", "author",
                                              "evidence", "route", "alpha_f")},
                         {"pid": 1, "family": fid, "version": 1, "lane": "beta", "reason": "train_pass", "ugroup": "index",
                          "lineage": elane.lineage_key("beta", fid), "author": "fake:author", "evidence": "registry",
                          "route": "S2", "alpha_f": "0.03"})
        self.assertEqual((row["code"], row["program_sha"], row["run_sha"]),
                         (version["code"], sha(version["code"]), run_sha(version)))
        self.assertEqual(json.loads(row["needs"]), {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2})
        self.assertEqual(row["needs"], results.canonical(json.loads(row["needs"])))
        self.assertEqual((row["created_at"], row["registered_at"]), (now, now))
        self.assertEqual((row["first_close"], row["first_day"]), (h.days[2].isoformat(), h.days[3].isoformat()))
        program = F.program(h.db, f"{fid}@1")
        self.assertEqual((program.params, program.needs["symbols"], program.lineage), ({"share": 0.25}, ["SPY"],
                                                                                    f"beta:{fid}"))

    def test_the_parameters_are_kept_exactly(self):
        # A figure beyond six places is not rounded: the shadow runs the very parameters, and the row's own code and
        # params give its run sha.
        h = House(self)
        params = {"alpha": 0.1234567891, "tiny": 1e-9, "n": 3, "name": "x"}
        fid = h.family("alpha", {1: FAILED}, params=params)
        h.sync()
        program = F.program(h.db, f"{fid}@1")
        self.assertEqual(program.params, params)
        self.assertNotEqual(json.loads(results.canonical(params)), params, "the canonical form would have rounded them")
        for p in F.programs(h.db, reasons=("train_fail",)):
            self.assertEqual(run_sha({"sha": p.program_sha, "params": p.params}), p.run_sha)

    def test_what_the_registry_froze_is_what_the_lane_loads(self):
        # The shadow slices its bars by the row's NEEDS and the decider child loads NEEDS from the row's code: one thing.
        from league.equity import program as P

        h = House(self)
        fid = h.family("alpha", {1: FAILED}, symbols=("IWM",), params={"share": 0.4})
        h.sync()
        row = F.program(h.db, f"{fid}@1")
        loaded = P.load_program(row.code, name=row.key, params=row.params)
        self.assertEqual(loaded.needs.as_dict(), row.needs)
        self.assertEqual((loaded.sha, loaded.params["share"]), (row.program_sha, 0.4))
        self.assertEqual(row.ugroup, elane_train.symbols_group(loaded.needs.symbols))

    def test_a_second_run_adds_nothing(self):
        h = House(self)
        a = h.family("alpha", {1: PASSED, 2: FAILED}, codes=2, passed_version=1)
        h.scored(a, 1, bar_passed=True)
        h.swarm.put(elane.SEEDS_KEY, {"seed-one": h.family("seeded", {}, lane="beta", symbols=("SPY",))})
        h.book(h.instance(a, 1))
        first = h.sync()
        self.assertEqual((first["registered"], first["controls"], first["tagged"]), (3, 3, 2))
        before = [tuple(r) for r in h.db.execute("SELECT * FROM fwd_registry ORDER BY pid")]
        events = h.db.execute("SELECT COUNT(*) FROM fwd_events").fetchone()[0]
        tags = h.db.execute("SELECT COUNT(*) FROM fwd_tags").fetchone()[0]
        for hours in (1, 2, 30):
            again = h.sync(h.clock() + 3600.0 * hours)
            self.assertEqual({k: again[k] for k in ("registered", "controls", "tagged", "stopped", "suspect", "skipped")},
                             {"registered": 0, "controls": 0, "tagged": 0, "stopped": 0, "suspect": 0, "skipped": []})
            self.assertEqual(again["chain"], first["chain"])
        self.assertEqual([tuple(r) for r in h.db.execute("SELECT * FROM fwd_registry ORDER BY pid")], before)
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM fwd_events").fetchone()[0], events)
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM fwd_tags").fetchone()[0], tags)

    def test_a_retired_family_is_registered_too(self):
        h = House(self)
        fid = h.family("alpha", {1: FAILED})
        h.swarm.retire(fid, "REFUTED on Train (an invented retirement)")
        self.assertEqual(h.sync()["registered"], 1)

    def test_the_public_readers(self):
        h = House(self)
        a = h.family("alpha", {1: PASSED, 2: UNJUDGED["DQ"]}, codes=2)
        b = h.family("beta", {1: REVIEW}, lane="beta", symbols=("SPY",))
        seq = h.scored(a, 1, bar_passed=True, when=at(h.days[1], 11))
        rows = {r["key"]: r for r in R.scored_versions(h.swarm)}
        self.assertEqual(set(rows), {f"{a}@1", f"{b}@1"})
        one = rows[f"{a}@1"]
        self.assertEqual({k: one[k] for k in ("family", "version", "lane", "lineage", "sha", "author", "bar_passed",
                                              "created_at", "evidence", "reason")},
                         {"family": a, "version": 1, "lane": "equity", "lineage": f"equity:{a}",
                          "sha": h.swarm.version(a, 1)["sha"], "author": "fake:author", "bar_passed": True,
                          "created_at": at(h.days[1], 11), "evidence": f"event:{seq}", "reason": "train_pass"})
        self.assertEqual((one["code"], one["params"], one["run_sha"]),
                         (h.swarm.version(a, 1)["code"], {}, run_sha(h.swarm.version(a, 1))))
        two = rows[f"{b}@1"]
        self.assertEqual((two["bar_passed"], two["reason"], two["evidence"], two["created_at"]),
                         (True, "train_pass", "registry", None), "the verdict's own bar_passed, with no event")
        self.assertEqual(R.seed_versions(h.swarm), [])
        self.assertEqual(R.live_instances(h.root / R.LIVE_DB), [], "no live book")
        self.assertEqual(R.instance_key(f"{a}@1:r"), f"{a}@1")

    def test_the_events_bar_passed_is_the_reason(self):
        # The event says what the bar said at scoring; the record may have moved since (a rescore, the review).
        h = House(self)
        a = h.family("alpha", {1: FAILED})
        b = h.family("beta", {1: PASSED})
        h.scored(a, 1, bar_passed=True)
        h.scored(b, 1, bar_passed=False)
        h.sync()
        self.assertEqual((h.row(f"{a}@1")["reason"], h.row(f"{b}@1")["reason"]), ("train_pass", "train_fail"))


class RetroOnlyWithAnEvent(unittest.TestCase):
    """T6 (the registry's half): no registry row claims a time before its evidence."""

    def test_with_its_scored_event_the_window_opens_at_the_events_close(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        scored_at = at(h.days[1], 15, 59)
        seq = h.scored(fid, 1, bar_passed=True, when=scored_at)
        h.sync(at(h.days[5], 10))                # the registry was down four sessions
        row = h.row(f"{fid}@1")
        self.assertEqual((row["evidence"], row["created_at"], row["registered_at"]),
                         (f"event:{seq}", scored_at, at(h.days[5], 10)))
        self.assertEqual((row["first_close"], row["first_day"]), (h.days[1].isoformat(), h.days[2].isoformat()))
        self.assertLess(dt.date.fromisoformat(row["first_day"]), h.days[5], "retro, on the swarm's own evidence")

    def test_a_minute_after_the_close_it_is_the_next_session(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        h.scored(fid, 1, bar_passed=True, when=at(h.days[1], 16, 1))
        h.sync(at(h.days[5], 10))
        row = h.row(f"{fid}@1")
        self.assertEqual((row["first_close"], row["first_day"]), (h.days[2].isoformat(), h.days[3].isoformat()))

    def test_without_an_event_its_time_is_the_registrys_own_sighting(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        h.swarm.event("swarm.elane", fid, {"pass": "train", "version": 1})          # another pass of E2's kind
        h.swarm.event("swarm.status", fid, {"pass": "scored", "version": 1})         # another kind
        seen = at(h.days[5], 10)
        h.sync(seen)
        row = h.row(f"{fid}@1")
        self.assertEqual((row["evidence"], row["created_at"], row["registered_at"]), ("registry", seen, seen))
        self.assertEqual((row["first_close"], row["first_day"]), (h.days[5].isoformat(), h.days[6].isoformat()))
        self.assertGreater(schedule.moments(row["first_close"]).close_at, seen, "no day before the registry saw it")

    def test_an_event_of_another_version_or_family_is_no_evidence(self):
        h = House(self)
        a = h.family("alpha", {1: FAILED, 2: FAILED}, codes=2)
        b = h.family("beta", {1: FAILED})
        early = at(h.days[1], 11)
        h.scored(a, 2, when=early)
        h.sync(at(h.days[5], 10))
        self.assertEqual(h.row(f"{a}@2")["evidence"], "event:1")
        for key in (f"{a}@1", f"{b}@1"):
            self.assertEqual((h.row(key)["evidence"], h.row(key)["created_at"]), ("registry", at(h.days[5], 10)), key)

    def test_an_event_that_names_another_code_is_refused_whole(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        h.scored(fid, 1, bar_passed=True, code_sha=sha("another program"), when=at(h.days[1], 11))
        out = h.sync(at(h.days[5], 10))
        self.assertIsNone(h.row(f"{fid}@1"), "never a row dated by an event that names other code")
        self.assertEqual(out["skipped"], [{"key": f"{fid}@1", "why": R.CAUSES["event_sha"]}])

    def test_the_earliest_event_is_the_time(self):
        h = House(self)
        fid = h.family("alpha", {1: FAILED})
        first = h.scored(fid, 1, when=at(h.days[1], 11))
        h.scored(fid, 1, when=at(h.days[3], 11))
        h.sync(at(h.days[5], 10))
        self.assertEqual((h.row(f"{fid}@1")["evidence"], h.row(f"{fid}@1")["created_at"]),
                         (f"event:{first}", at(h.days[1], 11)))

    def test_no_row_of_a_mixed_registry_claims_a_time_before_its_evidence(self):
        h = House(self)
        fids = [h.family(f"fam-{i}", {1: PASSED if i % 2 else FAILED}) for i in range(6)]
        for i, fid in enumerate(fids[:4]):
            h.scored(fid, 1, bar_passed=bool(i % 2), when=at(h.days[i], 9 + 2 * i))
        h.swarm.put(elane.SEEDS_KEY, {"seed-one": h.family("seeded", {}, lane="beta", symbols=("SPY",))})
        h.book(h.instance(fids[0], 1), {"id": "loner@3:r", "family": "loner", "version": 3, "code": fx.program("IWM"),
                                        "params": {}, "run_sha": run_sha({"sha": sha(fx.program("IWM")), "params": {}}),
                                        "created_at": at(h.days[0], 12)})
        h.sync(at(h.days[6], 10))
        scored = {int(r["seq"]): r for r in h.swarm._all("SELECT * FROM events WHERE kind='swarm.elane'")}
        rows = [dict(r) for r in h.db.execute("SELECT * FROM fwd_registry ORDER BY pid")]
        self.assertEqual(len(rows), 8 + 3)
        self.assertEqual({r["evidence"].split(":")[0] for r in rows}, {"event", "registry"})
        for row in rows:
            if row["evidence"] == "registry":
                self.assertEqual(row["created_at"], row["registered_at"], row["key"])
            else:
                event = scored[int(row["evidence"].split(":")[1])]
                payload = json.loads(event["payload"])
                self.assertEqual((event["family"], payload["version"], payload["sha"], payload["pass"]),
                                 (row["family"], row["version"], row["program_sha"], "scored"), row["key"])
                self.assertEqual(row["created_at"], dt.datetime.fromisoformat(
                    event["at"].replace("Z", "+00:00")).timestamp(), row["key"])
            close = F.first_close(row["created_at"])
            self.assertEqual((row["first_close"], row["first_day"]), (close.isoformat(), F.first_day(close).isoformat()))
            self.assertGreater(schedule.moments(row["first_close"]).close_at, row["created_at"], row["key"])
            self.assertGreaterEqual(dt.date.fromisoformat(row["first_day"]), F.t0())
        # A live instance the book created days ago is dated by the registry's sighting, not by the book's row.
        self.assertEqual((h.row("loner@3")["reason"], h.row("loner@3")["created_at"]), ("live", at(h.days[6], 10)))

    def test_pids_follow_the_order_the_programs_came_to_exist(self):
        # Oldest evidence first, whatever the families' own order; a version with no event after them.
        h = House(self)
        late = h.family("alpha", {1: PASSED})
        unseen = h.family("beta", {1: FAILED})
        early = h.family("zeta", {1: FAILED})
        h.scored(early, when=at(h.days[1], 10))
        h.scored(late, bar_passed=True, when=at(h.days[1], 11))
        h.sync(at(h.days[2], 10))
        self.assertEqual(h.keys(), [f"{early}@1", f"{late}@1", f"{unseen}@1"])
        self.assertEqual([h.row(key)["evidence"] for key in h.keys()], ["event:1", "event:2", "registry"])

    def test_a_version_older_than_the_look_cap_starts_at_t0(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        h.scored(fid, 1, bar_passed=True, when=at(dt.date(2026, 10, 5), 11))
        h.sync()
        self.assertEqual((h.row(f"{fid}@1")["first_close"], h.row(f"{fid}@1")["first_day"]),
                         (config.LOOK_CAP.isoformat(), F.t0().isoformat()))

    def test_the_chain_refuses_a_hand_made_retro_row(self):
        h = House(self)
        seen = at(h.days[5], 10)
        code = fx.program("SPY")
        close = F.first_close(at(h.days[1], 11))
        row = {"key": "hand@1", "family": "hand", "version": 1, "lane": "equity", "reason": "train_pass",
               "ugroup": "index", "lineage": "equity:hand", "code": code, "params": "{}",
               "needs": '{"symbols":["SPY"]}', "program_sha": sha(code), "run_sha": "x", "author": "",
               "created_at": at(h.days[1], 11), "evidence": "registry", "first_close": close,
               "first_day": F.first_day(close), "registered_at": seen, "route": "S2", "alpha_f": "0.03"}
        with self.assertRaises(ValueError):
            F.append_registry(h.db, row)
        with self.assertRaises(ValueError):       # nor a window earlier than its own time allows
            F.append_registry(h.db, {**row, "created_at": seen, "evidence": "event:1"})
        self.assertEqual(F.verify_chain(h.db)["rows"], 0)


class Refused(unittest.TestCase):
    def test_a_mismatched_sha_is_refused_and_its_event_written_once_over_many_runs(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        good = h.family("good", {1: FAILED})
        seq = h.scored(fid, 1, bar_passed=True, when=at(h.days[1], 11))
        path = h.root / h.swarm._one("SELECT path FROM versions WHERE family=?", (fid,))["path"]
        text = path.read_text()
        path.write_text(text + "\n# a line someone added after the version was stored\n")
        for i in range(6):
            out = h.sync(at(h.days[4], 10) + 3600.0 * i)
            self.assertEqual(out["skipped"], [{"key": f"{fid}@1", "why": R.CAUSES["sha"]}])
            self.assertIsNone(h.row(f"{fid}@1"))
        (event,) = F.events(h.db, "register_skipped")
        self.assertEqual((event["payload"]["key"], event["payload"]["cause"], event["at"]),
                         (f"{fid}@1", "sha", at(h.days[4], 10)))
        self.assertIsNotNone(h.row(f"{good}@1"), "one refused version never stops the others")
        # The program text read as stored again: registered, on its own event (which the cursor had passed).
        path.write_text(text)
        self.assertEqual(h.sync()["registered"], 1)
        self.assertEqual((h.row(f"{fid}@1")["evidence"], h.row(f"{fid}@1")["created_at"]),
                         (f"event:{seq}", at(h.days[1], 11)))
        self.assertEqual(len(F.events(h.db, "register_skipped")), 1)

    def test_a_program_text_that_cannot_be_read(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        (h.root / h.swarm._one("SELECT path FROM versions WHERE family=?", (fid,))["path"]).unlink()
        for _ in range(3):
            self.assertEqual(h.sync()["skipped"], [{"key": f"{fid}@1", "why": R.CAUSES["code"]}])
        self.assertEqual(len(F.events(h.db, "register_skipped")), 1)

    def test_needs_the_lane_does_not_accept(self):
        h = House(self)
        for slug, code in (("computed", fx.program("SPY").replace('NEEDS = {"symbols": ["SPY"], "history": 2, '
                                                                  '"max_hold_sessions": 2}', "NEEDS = dict(symbols=['SPY'])")),
                           ("outside", fx.program("SPY").replace('["SPY"]', '["ZZZZ"]')),
                           ("missing", "PARAMS = {}\n\n\ndef decide(ctx):\n    return []\n"),
                           ("broken", "def decide(ctx:\n")):
            fam = fx.e2_family(h.swarm, slug, lane="equity", agenda="trend", symbols=("SPY",))
            h.swarm.add_version(fam["id"], code, {}, author="fake:author")
            h.swarm.set_state(fam["id"], **{elane_train.STATE_KEY: {"versions": {"1": dict(FAILED)}}})
        out = h.sync()
        self.assertEqual(out["registered"], 0)
        self.assertEqual({(row["key"], row["why"]) for row in out["skipped"]},
                         {(f"{slug}@1", R.CAUSES["needs"]) for slug in ("computed", "outside", "missing", "broken")})
        h.sync()
        self.assertEqual(len(F.events(h.db, "register_skipped")), 4)

    def test_a_family_that_is_no_equity_structure(self):
        h = House(self)
        fid = h.family("alpha", {1: FAILED})
        fam = {**h.swarm.family(fid), "structure": "long_call"}
        with self.assertRaises(R._Refused) as raised:
            R._row(h.swarm, fam, 1, reason=None)
        self.assertEqual((raised.exception.cause, str(raised.exception)), ("structure", R.CAUSES["structure"]))
        with self.assertRaises(R._Refused) as raised:
            R._row(h.swarm, {**h.swarm.family(fid), "spec": {"lane": "options"}}, 1, reason=None)
        self.assertEqual(raised.exception.cause, "lane")
        with self.assertRaises(R._Refused) as raised:
            R._row(h.swarm, h.swarm.family(fid), 9, reason=None)
        self.assertEqual(raised.exception.cause, "version")

    def test_every_cause_has_its_words(self):
        for cause, words in R.CAUSES.items():
            self.assertTrue(words and not FIGURE.search(words), cause)


class SeedsAndLive(unittest.TestCase):
    def test_a_seed_is_registered_at_its_candidate_version(self):
        h = House(self)
        fid = h.family("seeded", {}, lane="beta", symbols=("SPY",), codes=2)
        h.swarm.put(elane.SEEDS_KEY, {"seed-overnight-spy": fid, "seed-gone": "no-such-family"})
        self.assertEqual([(r["key"], r["reason"]) for r in R.seed_versions(h.swarm)], [(f"{fid}@2", "seed")])
        h.swarm.update_family(fid, best_version=1)
        self.assertEqual([r["key"] for r in R.seed_versions(h.swarm)], [f"{fid}@1"])
        out = h.sync()
        self.assertEqual(out["registered"], 1)
        row = h.row(f"{fid}@1")
        self.assertEqual((row["reason"], row["evidence"], row["lane"], row["route"]), ("seed", "registry", "beta", "S2"))
        self.assertEqual(F.program(h.db, f"{fid}@1").run_sha, run_sha(h.swarm.version(fid, 1)))

    def test_a_live_instance_is_tagged_and_one_not_registered_is_registered_from_the_book(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        code = fx.program("IWM")
        params = {"share": 0.3}
        loner = {"id": "loner@3:r", "family": "loner", "version": 3, "lane": "beta", "code": code, "params": params,
                 "run_sha": run_sha({"sha": sha(code), "params": params}), "retired_at": 5.0}
        h.book(h.instance(fid, 1), loner)
        self.assertEqual([i["id"] for i in R.live_instances(h.root / R.LIVE_DB)], [f"{fid}@1:r", "loner@3:r"])
        self.assertEqual(R.live_instances(h.root / R.LIVE_DB)[1]["params"], params)
        out = h.sync()
        self.assertEqual((out["registered"], out["tagged"], out["skipped"]), (2, 2, []))
        row = h.row("loner@3")
        self.assertEqual({k: row[k] for k in ("reason", "family", "version", "lane", "code", "run_sha", "lineage",
                                              "evidence", "ugroup")},
                         {"reason": "live", "family": "loner", "version": 3, "lane": "beta", "code": code,
                          "run_sha": loner["run_sha"], "lineage": "beta:loner", "evidence": "registry", "ugroup": "index"})
        self.assertEqual(F.program(h.db, "loner@3").params, params)
        self.assertEqual(h.row(f"{fid}@1")["reason"], "train_pass", "a registered key keeps its row")
        self.assertEqual(F.tags(h.db, row["pid"]), {"live": [{"value": "loner@3:r", "at": h.clock()}]},
                         "a retired instance was seated: its tag stays")
        self.assertEqual(F.tags(h.db, 1)["live"], [{"value": f"{fid}@1:r", "at": h.clock()}])

    def test_an_instance_running_another_run_sha_is_not_tagged(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        h.book(h.instance(fid, 1, run_sha="f" * 64))
        for _ in range(3):
            out = h.sync()
            self.assertEqual(out["skipped"], [{"key": f"{fid}@1:r", "why": R.CAUSES["live_sha"]}])
        self.assertNotIn("live", F.tags(h.db, 1))
        self.assertEqual(len(F.events(h.db, "register_skipped")), 1)

    def test_a_book_row_whose_run_sha_is_not_its_codes_is_refused(self):
        h = House(self)
        code = fx.program("IWM")
        h.book({"id": "loner@1:r", "family": "loner", "version": 1, "code": code, "params": {}, "run_sha": "f" * 64},
               {"id": "odd@1:r", "family": "odd", "version": 1, "lane": "options", "code": code, "params": {},
                "run_sha": run_sha({"sha": sha(code), "params": {}})})
        out = h.sync()
        self.assertEqual((out["registered"], sorted((r["key"], r["why"]) for r in out["skipped"])),
                         (0, [("loner@1", R.CAUSES["run_sha"]), ("odd@1", R.CAUSES["lane"])]))

    def test_a_book_from_before_the_equity_lane(self):
        h = House(self)
        sqlite3.connect(str(h.root / R.LIVE_DB)).close()
        self.assertEqual(R.live_instances(h.root / R.LIVE_DB), [])
        db = sqlite3.connect(str(h.root / R.LIVE_DB))
        db.execute("CREATE TABLE positions (pid INTEGER PRIMARY KEY)")
        db.commit()
        db.close()
        self.assertEqual(R.live_instances(h.root / R.LIVE_DB), [])
        self.assertEqual(h.sync()["skipped"], [])


class Controls(unittest.TestCase):
    def test_they_arrive_with_the_groups_first_program_and_none_for_an_empty_group(self):
        h = House(self)
        self.assertEqual(h.sync()["controls"], 0, "no program yet: no control")
        h.family("alpha", {1: FAILED}, symbols=("QQQ",))
        out = h.sync()
        self.assertEqual((out["registered"], out["controls"]), (1, 3))
        self.assertEqual(h.keys("reason = 'control'"), ["control:index:0", "control:index:1", "control:index:2"])
        self.assertEqual(h.sync()["controls"], 0)
        # A second index program brings none; the first sector program brings its group's; a stock group that the
        # universe holds no symbol of has none.
        h.family("beta", {1: FAILED}, symbols=("SPY",))
        self.assertEqual(h.sync()["controls"], 0)
        h.family("gamma", {1: FAILED}, symbols=("XLK",))
        h.family("delta", {1: FAILED}, symbols=("AAPL",))
        out = h.sync()
        self.assertEqual((out["registered"], out["controls"]), (2, 3))
        self.assertEqual(h.row("delta@1")["ugroup"], "stocks")
        self.assertEqual(sorted(h.keys("reason = 'control'")),
                         sorted(f"control:{g}:{n}" for g in ("index", "sectors") for n in range(3)))

    def test_a_program_over_two_groups_brings_both(self):
        h = House(self)
        fam = fx.e2_family(h.swarm, "pair", lane="equity", agenda="rotation", symbols=("SPY", "TLT"))
        h.swarm.add_version(fam["id"], fx.program("SPY").replace('["SPY"]', '["SPY", "TLT"]'), {}, author="fake:author")
        h.swarm.set_state(fam["id"], **{elane_train.STATE_KEY: {"versions": {"1": dict(FAILED)}}})
        out = h.sync()
        self.assertEqual((h.row("pair@1")["ugroup"], out["controls"]), ("index+defensive", 6))

    def test_a_controls_row(self):
        h = House(self)
        h.family("alpha", {1: FAILED})
        now = h.clock()
        h.sync()
        row = h.row("control:index:1")
        symbols = C.group_symbols("index", UNIVERSE)
        self.assertEqual({k: row[k] for k in ("family", "version", "lane", "reason", "ugroup", "lineage", "author",
                                              "evidence", "route", "alpha_f", "params")},
                         {"family": None, "version": None, "lane": "control", "reason": "control", "ugroup": "index",
                          "lineage": "control:index:1", "author": "house", "evidence": "registry", "route": "none",
                          "alpha_f": "0", "params": "{}"})
        self.assertEqual(row["code"], results.canonical(C.spec("index", 1, symbols)))
        self.assertEqual((row["program_sha"], row["run_sha"]), (sha(row["code"]), sha(row["code"])))
        self.assertEqual(json.loads(row["needs"]), {"symbols": list(symbols), "history": 1, "max_hold_sessions": 20})
        self.assertEqual((row["created_at"], row["registered_at"]), (now, now))
        self.assertEqual((row["first_close"], row["first_day"]), (h.days[2].isoformat(), h.days[3].isoformat()))
        # What the shadow draws its lots from is the frozen spec.
        program = F.program(h.db, "control:index:1")
        spec = json.loads(program.code)
        self.assertEqual((spec, program.needs["symbols"]), (C.spec("index", 1, symbols), list(symbols)))
        self.assertIsInstance(C.control_lots(spec, h.days[2:12]), list)

    def test_the_setting_is_the_number_a_group(self):
        h = House(self, controls_per_group=0)
        h.family("alpha", {1: FAILED})
        self.assertEqual(h.sync()["controls"], 0)
        h.settings["elane"]["forward"]["controls_per_group"] = 50
        self.assertEqual(h.sync()["controls"], 50)
        self.assertEqual(h.sync()["controls"], 0)
        codes = [json.loads(r["code"]) for r in h.db.execute("SELECT code FROM fwd_registry WHERE reason='control' "
                                                             "ORDER BY pid")]
        self.assertEqual([c["n"] for c in codes], list(range(50)))
        self.assertEqual(sorted({c["f"] for c in codes}), list(C.F_GRID))

    def test_a_run_cut_short_is_finished_by_the_next(self):
        h = House(self)
        h.family("alpha", {1: FAILED})
        real = F.append_registry
        calls = []

        def cut(db, row):
            calls.append(row["key"])
            if row["key"] == "control:index:1":
                raise KeyboardInterrupt("the House restarted mid-run")
            return real(db, row)

        with mock.patch.object(F, "append_registry", cut):
            with self.assertRaises(KeyboardInterrupt):
                h.sync()
        self.assertEqual(h.keys("1=1"), ["alpha@1", "control:index:0"])
        self.assertTrue(F.verify_chain(h.db)["ok"], "each insert is one transaction: the chain holds after the cut")
        out = h.sync()
        self.assertEqual((out["registered"], out["controls"], out["chain"]["rows"]), (0, 2, 4))

    def test_a_control_never_stops(self):
        h = House(self, stop_after_sessions=20, stop_fail_after_sessions=20)
        h.family("alpha", {1: FAILED})
        h.sync()
        engine = h.engine()
        control = F.program(h.db, "control:index:0").pid
        h.stored(control, 40, engine=engine)
        out = h.sync()
        self.assertEqual(out["stopped"], 0)
        self.assertTrue(F.active(h.db, control))


class Tags(unittest.TestCase):
    def test_the_facts_learned_later(self):
        h = House(self)
        a = h.family("alpha", {1: FAILED, 2: PASSED, 3: REVIEW}, codes=3, passed_version=2)
        b = h.family("beta", {1: PASSED}, passed_version=1)
        c = h.family("gamma", {1: FAILED})
        first = h.clock()
        self.assertEqual(h.sync()["tagged"], 3)
        pid = {key: h.row(key)["pid"] for key in h.keys()}
        self.assertEqual(F.tags(h.db, pid[f"{a}@2"]), {"review_pass": [{"value": "", "at": first}]})
        self.assertEqual(F.tags(h.db, pid[f"{a}@3"]), {"review_fail": [{"value": "", "at": first}]})
        self.assertEqual(F.tags(h.db, pid[f"{a}@1"]), {})
        # Later: alpha's pass takes its Validation try and enters the gate; beta's is tried and stays out; then the looks.
        h.swarm.set_state(a, **{elane.TRY_KEY: {"version": 2, "entered": True, "precheck": True},
                                elane.VERDICTS_KEY: {"2": {"entered": True, "at": "x", "stale": False}}})
        h.swarm.set_state(b, **{elane.TRY_KEY: {"version": 1, "entered": False, "precheck": False}})
        later = first + 7200.0
        self.assertEqual(h.sync(later)["tagged"], 3)
        self.assertEqual({k: v[0]["at"] for k, v in F.tags(h.db, pid[f"{a}@2"]).items()},
                         {"review_pass": first, "try": later, "try_entered": later})
        self.assertEqual(set(F.tags(h.db, pid[f"{b}@1"])), {"review_pass", "try"})
        h.swarm.set_state(a, **{elane.LOOK_KEY: {"version": 2, "verdict": {"passed": True}, "beside": "x"}})
        h.swarm.set_state(b, **{elane.LOOK_KEY: {"version": 1, "verdict": {"passed": False}, "beside": "x"}})
        h.swarm.set_state(c, **{elane.LOOK_KEY: {"version": 7, "verdict": {"passed": True}, "beside": "x"}})
        last = later + 7200.0
        self.assertEqual(h.sync(last)["tagged"], 2)
        self.assertEqual(F.tags(h.db, pid[f"{a}@2"])["look_pass"], [{"value": "", "at": last}])
        self.assertEqual(F.tags(h.db, pid[f"{b}@1"])["look_fail"], [{"value": "", "at": last}])
        self.assertEqual(F.tags(h.db, pid[f"{c}@1"]), {}, "a look of another version is not this program's")
        self.assertEqual(h.sync(last + 3600.0)["tagged"], 0)

    def test_a_verdict_kept_for_an_earlier_try_is_a_try_too(self):
        # R3's retry replaces the family's try record within the hour: each version's own verdict still names it.
        h = House(self)
        a = h.family("alpha", {1: PASSED, 2: PASSED}, codes=2, passed_version=1)
        h.swarm.set_state(a, **{elane.TRY_KEY: {"version": 2, "entered": True},
                                elane.VERDICTS_KEY: {"1": {"entered": False}, "2": {"entered": True}}})
        h.sync()
        self.assertEqual(set(F.tags(h.db, h.row(f"{a}@1")["pid"])), {"review_pass", "try"})
        self.assertEqual(set(F.tags(h.db, h.row(f"{a}@2")["pid"])), {"try", "try_entered"})


class StopRules(unittest.TestCase):
    def house(self) -> tuple[House, int, int]:
        h = House(self, stop_after_sessions=25, stop_fail_after_sessions=20)
        a = h.family("alpha", {1: PASSED})
        b = h.family("beta", {1: FAILED})
        h.sync()
        return h, h.row(f"{a}@1")["pid"], h.row(f"{b}@1")["pid"]

    def test_the_cap_on_stored_days(self):
        h, passer, failer = self.house()
        engine = h.engine()
        h.stored(passer, 19, engine=engine)
        h.stored(failer, 19, engine=engine, status="disqualified")
        self.assertEqual(h.sync()["stopped"], 0)
        h.stored(passer, 1, engine=engine, first=19)
        h.stored(failer, 1, engine=engine, first=19, status="disqualified")
        out = h.sync()
        self.assertEqual(out["stopped"], 1, "a non-passer stops at 20 STORED days, whatever their status")
        self.assertFalse(F.active(h.db, failer))
        self.assertTrue(F.active(h.db, passer), "a passer's cap is the longer one")
        self.assertEqual(F.tags(h.db, failer)["stopped"], [{"value": f"cap:{h.days[19].isoformat()}", "at": h.clock()}])
        (event,) = F.events(h.db, "stopped")
        self.assertEqual((event["pid"], event["day"], event["payload"]["cause"], event["payload"]["sessions"],
                          event["payload"]["cap"]), (failer, h.days[19].isoformat(), "cap", 20, 20))
        h.stored(passer, 5, engine=engine, first=20)
        self.assertEqual(h.sync()["stopped"], 1)
        self.assertFalse(F.active(h.db, passer))
        self.assertEqual(h.sync()["stopped"], 0, "a stop is written once")
        self.assertEqual(len(F.events(h.db, "stopped")), 2)
        self.assertEqual([p.key for p in F.programs(h.db, reasons=("train_pass", "train_fail"))], [])

    def test_the_cap_counts_the_newest_engine(self):
        h, passer, failer = self.house()
        old = h.engine("engine-a")
        h.stored(failer, 19, engine=old)
        new = h.engine("engine-b")
        h.stored(failer, 5, engine=new)
        self.assertEqual(h.sync()["stopped"], 0, "the old series is never read as the current one")
        h.stored(failer, 15, engine=new, first=5)
        self.assertEqual(h.sync()["stopped"], 1)

    def test_seeds_and_live_programs_have_the_passers_cap(self):
        h = House(self, stop_after_sessions=25, stop_fail_after_sessions=20)
        fid = h.family("seeded", {}, lane="beta", symbols=("SPY",))
        h.swarm.put(elane.SEEDS_KEY, {"seed-one": fid})
        code = fx.program("IWM")
        h.book({"id": "loner@1:r", "family": "loner", "version": 1, "code": code, "params": {},
                "run_sha": run_sha({"sha": sha(code), "params": {}})})
        h.sync()
        engine = h.engine()
        for key in (f"{fid}@1", "loner@1"):
            h.stored(h.row(key)["pid"], 24, engine=engine)
        self.assertEqual(h.sync()["stopped"], 0)
        for key in (f"{fid}@1", "loner@1"):
            h.stored(h.row(key)["pid"], 1, engine=engine, first=24)
        self.assertEqual(h.sync()["stopped"], 2)

    def test_three_disqualified_nights_running(self):
        h, passer, failer = self.house()
        h.night(3, marks={passer: "run_disqualified"})
        h.night(4, marks={passer: "run_disqualified", failer: "run_disqualified"})
        self.assertEqual(h.sync()["stopped"], 0, "two nights are not three")
        h.night(5, marks={failer: "run_disqualified"}, ran={passer: "ok"})    # the passer ran clean that night
        self.assertEqual(h.sync()["stopped"], 0)
        h.night(6, marks={passer: "run_disqualified", failer: "run_disqualified"})
        out = h.sync()
        self.assertEqual(out["stopped"], 1)
        self.assertEqual(F.tags(h.db, failer)["stopped"][0]["value"], f"disqualified:{h.days[6].isoformat()}")
        self.assertTrue(F.active(h.db, passer), "a clean night between breaks the run of three")
        (event,) = F.events(h.db, "stopped")
        self.assertEqual((event["pid"], event["payload"]["cause"], event["payload"]["nights"]), (failer, "disqualified", 3))
        h.night(7, marks={passer: "run_disqualified"})
        h.night(8, marks={passer: "run_disqualified"})
        self.assertEqual(h.sync()["stopped"], 1)
        self.assertEqual(F.tags(h.db, passer)["stopped"][0]["value"], f"disqualified:{h.days[8].isoformat()}")

    def test_the_nights_are_the_programs_own_a_night_that_left_it_stale_is_none(self):
        """The review's finding: on nights the budget binds a program is run every other night or less. Counted by
        the calendar, "an event on each of the last three nights" never held, and a program disqualified at every
        run was run whole for the life of the House."""
        h, passer, failer = self.house()
        dq = {"marks": {passer: "run_disqualified"}, "ran": {passer: "disqualified"}}
        h.night(3, **dq)
        h.night(4)                                   # the budget left it stale: no row, no event
        h.night(5, **dq)                             # its row for night 4's day is written here, by night 5's run
        h.night(6)
        self.assertEqual(h.sync()["stopped"], 0, "two runs are not three")
        through = h.night(7, **dq)
        out = h.sync()
        self.assertEqual(out["stopped"], 1, "disqualified at each of its last three runs, five nights apart")
        self.assertEqual(F.tags(h.db, passer)["stopped"][0]["value"], f"disqualified:{through}")
        self.assertTrue(F.active(h.db, failer))
        (event,) = F.events(h.db, "stopped")
        self.assertIn("its own attempted nights", event["payload"]["why"])

    def test_a_clean_run_between_breaks_the_run_whichever_night_it_was(self):
        h, passer, _ = self.house()
        dq = {"marks": {passer: "run_disqualified"}, "ran": {passer: "disqualified"}}
        h.night(3, **dq)
        h.night(4)
        h.night(5, **dq)
        h.night(6, ran={passer: "ok"})               # a run of it completed clean: its own night, and it breaks the run
        h.night(7, **dq)
        self.assertEqual(h.sync()["stopped"], 0)
        h.night(8)
        h.night(9, **dq)
        self.assertEqual(h.sync()["stopped"], 0, "two since the clean run")
        h.night(10, **dq)
        self.assertEqual(h.sync()["stopped"], 1)

    def test_a_night_the_child_failed_it_says_nothing_of_what_the_program_does(self):
        # Disqualified, failed in the child, disqualified, disqualified: its last three COMPLETED runs were its own.
        h, passer, _ = self.house()
        dq = {"marks": {passer: "run_disqualified"}, "ran": {passer: "disqualified"}}
        h.night(3, **dq)
        h.night(4, marks={passer: "run_failed"})
        h.night(5, **dq)
        self.assertEqual(h.sync()["stopped"], 0)
        h.night(6, **dq)
        out = h.sync()
        self.assertEqual((out["stopped"], out["suspect"]), (1, 0))

    def test_three_failed_nights_of_its_own_give_suspect_however_far_apart(self):
        """A program the child cannot finish, attempted every other night: three attempts running, all failed."""
        h, passer, failer = self.house()
        for index in (3, 5):
            h.night(index, marks={passer: "run_failed"})
            h.night(index + 1, ran={failer: "ok"})   # nights it was left stale; another program's runs completed
        self.assertEqual(h.sync()["suspect"], 0)
        through = h.night(7, marks={passer: "run_failed"})
        out = h.sync()
        self.assertEqual((out["suspect"], out["stopped"]), (1, 0))
        self.assertEqual(F.tags(h.db, passer)["suspect"], [{"value": through, "at": h.clock()}])
        self.assertFalse(F.suspect(h.db, failer))
        (event,) = F.events(h.db, "suspect")
        self.assertIn("attempted nights", event["payload"]["why"])

    def test_a_completed_run_between_two_failed_nights_breaks_the_run(self):
        h, passer, _ = self.house()
        h.night(3, marks={passer: "run_failed"})
        h.night(4, marks={passer: "run_failed"})
        h.night(5, ran={passer: "ok"})
        h.night(6, marks={passer: "run_failed"})
        self.assertEqual(h.sync()["suspect"], 0)
        h.night(7, marks={passer: "run_failed"})
        self.assertEqual(h.sync()["suspect"], 0)
        h.night(8, marks={passer: "run_failed"})
        self.assertEqual(h.sync()["suspect"], 1)

    def test_a_run_behind_event_marks_nobody(self):
        h, passer, _ = self.house()
        for index in range(3, 12):
            h.night(index, programs=0, marks={passer: "run_behind"})
            out = h.sync()
            self.assertEqual((out["stopped"], out["suspect"]), (0, 0))
        self.assertTrue(F.active(h.db, passer))
        self.assertFalse(F.suspect(h.db, passer))

    def test_the_night_is_read_from_the_events_key_when_it_has_no_day(self):
        h, passer, _ = self.house()
        for index in (3, 4, 5):
            through = h.night(index)
            F.event(h.db, "run_disqualified", pid=passer, payload={"why": "invented"}, at=h.clock(), once=through)
        self.assertEqual(h.sync()["stopped"], 1)

    def test_three_failed_nights_give_suspect_never_stopped(self):
        h, passer, failer = self.house()
        for index in (3, 4):
            h.night(index, marks={passer: "run_failed"})
        self.assertEqual(h.sync()["suspect"], 0)
        through = h.night(5, marks={passer: "run_failed"})
        out = h.sync()
        self.assertEqual((out["suspect"], out["stopped"]), (1, 0))
        self.assertTrue(F.active(h.db, passer), "a failure never stops a program")
        self.assertTrue(F.suspect(h.db, passer))
        self.assertFalse(F.suspect(h.db, failer))
        self.assertEqual(F.tags(h.db, passer)["suspect"], [{"value": through, "at": h.clock()}])
        (event,) = F.events(h.db, "suspect")
        self.assertEqual((event["pid"], event["day"]), (passer, through))
        self.assertEqual(h.sync()["suspect"], 0, "once a night")
        # A fourth failed night is one more tag; ten more failed nights never stop it.
        for index in range(6, 16):
            h.night(index, marks={passer: "run_failed"})
            h.sync()
        self.assertTrue(F.active(h.db, passer))
        self.assertEqual(len(F.tags(h.db, passer)["suspect"]), 11)
        self.assertEqual(F.events(h.db, "stopped"), [])
        # The night it completes a run it stores that day, and is suspect no more.
        h.stored(passer, 17, engine=h.engine())
        self.assertFalse(F.suspect(h.db, passer))

    def test_a_night_no_program_completed_is_the_houses(self):
        # `run_failed` is written only while another program's run completed; a night whose row says none did counts
        # toward nothing, whatever events it holds.
        h, passer, _ = self.house()
        h.night(3, marks={passer: "run_failed"})
        h.night(4, programs=0, marks={passer: "run_failed"})
        h.night(5, marks={passer: "run_failed"})
        self.assertEqual(h.sync()["suspect"], 0, "two nights with a completed program are not three")
        h.night(6, marks={passer: "run_failed"})
        self.assertEqual(h.sync()["suspect"], 1)

    def test_night_failed_and_data_failed_mark_no_program(self):
        h, passer, failer = self.house()
        for index in range(3, 12):
            through = h.night(index, marks={passer: "data_failed"})
            F.event(h.db, "night_failed", day=through, payload={"why": "the decider did not start"}, at=h.clock(),
                    once=through)
            out = h.sync()
            self.assertEqual((out["stopped"], out["suspect"]), (0, 0))
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM fwd_tags WHERE tag IN ('stopped', 'suspect')").fetchone()[0], 0)
        self.assertTrue(F.active(h.db, passer) and F.active(h.db, failer))

    def test_a_resume_makes_it_active_and_old_nights_no_longer_count(self):
        h, passer, failer = self.house()
        for index in (3, 4, 5):
            h.night(index, marks={failer: "run_disqualified", passer: "run_failed"})
        out = h.sync()
        self.assertEqual((out["stopped"], out["suspect"]), (1, 1))
        self.assertFalse(R.resume(h.db, "no-such@1", why="x", at=h.clock()), "an unknown key")
        self.assertFalse(R.resume(h.db, h.row("alpha@1")["key"], why="x", at=h.clock()), "nothing to undo")
        when = h.clock() + 600.0
        self.assertTrue(R.resume(h.db, "beta@1", why="the  operator\nfixed its data", at=when))
        self.assertTrue(F.active(h.db, failer))
        self.assertEqual(F.tags(h.db, failer)["resumed"], [{"value": f"{when!r}|the operator fixed its data", "at": when}])
        (event,) = F.events(h.db, "resumed")
        self.assertEqual((event["pid"], event["payload"]["key"], event["payload"]["why"]),
                         (failer, "beta@1", "the operator fixed its data"))
        self.assertEqual(h.sync(when + 60.0)["stopped"], 0, "the three old nights no longer count")
        self.assertFalse(R.resume(h.db, "beta@1", why="again", at=when + 120.0), "it is not stopped now")
        # Two new disqualified nights are not three; the third stops it again.
        h.night(6, marks={failer: "run_disqualified"})
        h.night(7, marks={failer: "run_disqualified"})
        self.assertEqual(h.sync()["stopped"], 0)
        h.night(8, marks={failer: "run_disqualified"})
        self.assertEqual(h.sync()["stopped"], 1)
        self.assertEqual([t["value"] for t in F.tags(h.db, failer)["stopped"]],
                         [f"disqualified:{h.days[5].isoformat()}", f"disqualified:{h.days[8].isoformat()}"])

    def test_a_night_whose_event_is_older_than_the_resume_is_an_old_night(self):
        # Whenever its `fwd_runs` row landed: the event is the program's own doing that night, and the undo came after it.
        h, _, failer = self.house()
        for index in (3, 4, 5):
            h.night(index, marks={failer: "run_disqualified"})
        self.assertEqual(h.sync()["stopped"], 1)
        through = h.days[6].isoformat()
        h.clock.t = at(h.days[6], 19)
        F.event(h.db, "run_disqualified", pid=failer, day=through, payload={"why": "an invented night"}, at=h.clock(),
                once="night")
        self.assertTrue(R.resume(h.db, "beta@1", why="resumed while the night was running", at=h.clock() + 600.0))
        h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs) VALUES("
                     "'forward_shadow', ?, 1, ?, ?, 1.0, 1)", (through, h.clock() - 60.0, h.clock() + 1200.0))
        h.db.commit()
        h.night(7, marks={failer: "run_disqualified"})
        h.night(8, marks={failer: "run_disqualified"})
        self.assertEqual(h.sync()["stopped"], 0, "two nights since the resume are not three")
        h.night(9, marks={failer: "run_disqualified"})
        self.assertEqual(h.sync()["stopped"], 1)
        self.assertEqual(F.tags(h.db, failer)["stopped"][-1]["value"], f"disqualified:{h.days[9].isoformat()}")

    def test_after_a_resume_the_cap_counts_only_days_stored_since(self):
        h, _, failer = self.house()
        engine = h.engine()
        h.stored(failer, 20, engine=engine, written=h.clock())
        self.assertEqual(h.sync()["stopped"], 1)
        when = h.clock() + 600.0
        self.assertTrue(R.resume(h.db, "beta@1", why="keep it running", at=when))
        self.assertEqual(h.sync(when + 60.0)["stopped"], 0)
        h.stored(failer, 19, engine=engine, first=20, written=when + 3600.0)
        self.assertEqual(h.sync(when + 7200.0)["stopped"], 0, "19 days since the resume")
        # An engine move writes its whole history again under a new id: the days stored before the resume stay old.
        new = h.engine("engine-b")
        h.stored(failer, 39, engine=new, written=when + 9000.0)
        self.assertEqual(h.sync(when + 9600.0)["stopped"], 0)
        h.stored(failer, 1, engine=new, first=39, written=when + 9900.0)
        self.assertEqual(h.sync(when + 10000.0)["stopped"], 1)
        self.assertEqual(F.tags(h.db, failer)["stopped"][-1]["value"], f"cap:{h.days[39].isoformat()}")


class TheCursor(unittest.TestCase):
    def test_it_moves_past_the_rows_handled(self):
        h = House(self)
        a = h.family("alpha", {1: FAILED})
        self.assertIsNone(F.kv_get(h.db, "scored_seq"))
        first = h.scored(a, 1, when=at(h.days[1], 11))
        h.sync(at(h.days[2], 10))
        self.assertEqual(F.kv_get(h.db, "scored_seq"), first)
        b = h.family("beta", {1: PASSED})
        h.swarm.event("swarm.elane", b, {"pass": "births", "n": 1})
        second = h.scored(b, 1, bar_passed=True, when=at(h.days[2], 11))
        read = []
        real = R._scored_events
        with mock.patch.object(R, "_scored_events", lambda store, **kw: read.append(kw) or real(store, **kw)):
            out = h.sync(at(h.days[2], 12))
        self.assertEqual(read, [{"after": first}, {"family": b}],
                         "the events after the cursor, and the whole log of a family with a version still to register")
        self.assertEqual((out["registered"], h.row(f"{b}@1")["evidence"], F.kv_get(h.db, "scored_seq")),
                         (1, f"event:{second}", second))
        read.clear()
        with mock.patch.object(R, "_scored_events", lambda store, **kw: read.append(kw) or real(store, **kw)):
            self.assertEqual(h.sync()["registered"], 0)
        self.assertEqual(read, [{"after": second}], "with nothing to register, only the events after the cursor")

    def test_the_earliest_event_is_the_time_even_when_the_cursor_passed_it(self):
        h = House(self)
        a = h.family("alpha", {1: FAILED})
        path = h.root / h.swarm._one("SELECT path FROM versions WHERE family=?", (a,))["path"]
        text = path.read_text()
        path.write_text(text + "# unreadable as stored\n")
        first = h.scored(a, 1, when=at(h.days[1], 11))
        self.assertEqual(h.sync(at(h.days[2], 10))["registered"], 0)      # refused; the cursor passes its event
        self.assertEqual(F.kv_get(h.db, "scored_seq"), first)
        h.scored(a, 1, when=at(h.days[3], 11))                             # a second event for the same version
        path.write_text(text)
        self.assertEqual(h.sync(at(h.days[4], 10))["registered"], 1)
        self.assertEqual((h.row(f"{a}@1")["evidence"], h.row(f"{a}@1")["created_at"]),
                         (f"event:{first}", at(h.days[1], 11)))

    def test_a_verdict_seen_before_its_event_is_dated_by_the_registry(self):
        # The swarm writes the record, then the event: a run between the two registers the version at its own sighting,
        # and the event that lands afterwards moves nothing (the first row stands).
        h = House(self)
        a = h.family("alpha", {1: FAILED})
        seen = h.clock()
        h.sync()
        h.scored(a, 1, when=seen + 5.0)
        self.assertEqual(h.sync(seen + 3600.0)["registered"], 0)
        self.assertEqual((h.row(f"{a}@1")["evidence"], h.row(f"{a}@1")["created_at"]), ("registry", seen))

    def test_an_event_the_record_does_not_hold_yet_is_found_later(self):
        h = House(self)
        a = h.family("alpha", {})
        seq = h.scored(a, 1, when=at(h.days[1], 11))            # read by a run whose record scan missed the verdict
        self.assertEqual(h.sync(at(h.days[2], 10))["registered"], 0)
        self.assertEqual(F.kv_get(h.db, "scored_seq"), seq)
        h.swarm.set_state(a, **{elane_train.STATE_KEY: {"versions": {"1": dict(FAILED)}}})
        self.assertEqual(h.sync(at(h.days[2], 11))["registered"], 1)
        self.assertEqual((h.row(f"{a}@1")["evidence"], h.row(f"{a}@1")["created_at"]), (f"event:{seq}", at(h.days[1], 11)))

    def test_an_event_that_cannot_be_read_is_no_evidence(self):
        h = House(self)
        a = h.family("alpha", {1: FAILED})
        for payload in ({"pass": "scored", "version": "1", "sha": h.swarm.version(a, 1)["sha"]},
                        {"pass": "scored", "version": True}, {"pass": "scored"}, ["scored"]):
            h.swarm.event("swarm.elane", a, payload)
        h.swarm._exec("INSERT INTO events(at, kind, family, payload) VALUES('not a time', 'swarm.elane', ?, ?)",
                      (a, json.dumps({"pass": "scored", "version": 1, "sha": h.swarm.version(a, 1)["sha"]})))
        h.sync()
        self.assertEqual(h.row(f"{a}@1")["evidence"], "registry")


class WhoseFailure(unittest.TestCase):
    def test_no_swarm_store_registers_nothing_and_fails_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = F.open_db(tmp)
            try:
                out = R.sync(tmp, db, now=at(F.t0(), 10), settings=None)
            finally:
                db.close()
        self.assertEqual({k: v for k, v in out.items() if k != "chain"},
                         {"registered": 0, "controls": 0, "tagged": 0, "stopped": 0, "suspect": 0, "skipped": []})
        self.assertEqual(out["chain"], {"ok": True, "rows": 0, "head": F.GENESIS, "first_bad": None})

    def test_an_unreadable_swarm_store_is_the_houses_and_the_stop_rules_still_run(self):
        h = House(self, stop_after_sessions=25, stop_fail_after_sessions=20)
        fid = h.family("alpha", {1: FAILED})
        h.sync()
        h.stored(1, 20, engine=h.engine())
        with mock.patch.object(R, "_families", side_effect=sqlite3.OperationalError("database is locked")):
            out = h.sync()
        self.assertEqual(out["skipped"], [{"key": R.SWARM_DB, "why": "the swarm store could not be read "
                                                                    "(OperationalError): nothing registered from it this run"}])
        self.assertEqual((out["stopped"], out["chain"]["ok"]), (1, True))
        self.assertEqual(F.events(h.db, "register_skipped"), [], "no version is refused for the House's failure")
        self.assertFalse(F.active(h.db, h.row(f"{fid}@1")["pid"]))

    def test_nothing_is_tagged_from_a_run_that_could_not_read_the_swarm_store(self):
        # The tags are one run's reading of the swarm store and the book together: the run that read only the book
        # writes none (a live tag neither), and the next run that reads both writes it.
        h = House(self)
        fid = h.family("alpha", {1: FAILED})
        h.sync()
        h.book(h.instance(fid))
        with mock.patch.object(R, "_families", side_effect=sqlite3.OperationalError("database is locked")):
            out = h.sync()
        self.assertEqual((out["tagged"], [row["key"] for row in out["skipped"]]), (0, [R.SWARM_DB]))
        self.assertNotIn("live", F.tags(h.db, h.row(f"{fid}@1")["pid"]))
        self.assertEqual(h.sync()["tagged"], 1)
        self.assertEqual(F.tags(h.db, h.row(f"{fid}@1")["pid"])["live"][0]["value"], f"{fid}@1:r")

    def test_a_live_instance_waits_for_a_run_that_can_read_its_lineage(self):
        # The registry is append-only: a live instance is never registered under a lineage the swarm could not say.
        h = House(self)
        code = fx.program("IWM")
        h.book({"id": "loner@1:r", "family": "loner", "version": 1, "code": code, "params": {},
                "run_sha": run_sha({"sha": sha(code), "params": {}})})
        with mock.patch.object(R, "_families", side_effect=sqlite3.OperationalError("database is locked")):
            out = h.sync()
        self.assertEqual((out["registered"], out["tagged"], [row["key"] for row in out["skipped"]]), (0, 0, [R.SWARM_DB]))
        self.assertIsNone(h.row("loner@1"))
        out = h.sync()
        self.assertEqual((out["registered"], out["tagged"], out["skipped"]), (1, 1, []))
        self.assertEqual(h.row("loner@1")["lineage"], "beta:loner")

    def test_a_live_instances_lineage_is_its_familys(self):
        h = House(self)
        parent = h.family("alpha", {})
        child = h.swarm.add_family({"id": "alpha-fork", "mechanism": "An invented fork of alpha: the same mechanism on IWM.",
                                    "structure": "etf", "roots": ["IWM"], "symbols": ["IWM"], "lane": "equity"},
                                   origin="fork", parent=parent)["id"]
        h.swarm.add_version(child, fx.program("IWM"), {}, author="fake:author")
        h.book(h.instance(child, 1, lane="equity"))
        self.assertEqual(h.sync()["registered"], 1)
        self.assertEqual(h.row(f"{child}@1")["lineage"], f"equity:{parent}", "the fork counts with its parent's lineage")

    def test_an_unreadable_live_book_is_the_houses(self):
        h = House(self)
        h.family("alpha", {1: FAILED})
        (h.root / R.LIVE_DB).write_bytes(b"this is not a database, " * 50)
        out = h.sync()
        self.assertEqual((out["registered"], [row["key"] for row in out["skipped"]]), (1, [R.LIVE_DB]))
        self.assertNotRegex(out["skipped"][0]["why"], FIGURE)
        self.assertEqual(F.events(h.db, "register_skipped"), [])

    def test_one_row_the_chain_refuses_never_stops_the_others(self):
        h = House(self)
        h.family("alpha", {1: FAILED})
        h.family("beta", {1: FAILED})
        real = F.append_registry

        def picky(db, row):
            if row["key"] == "alpha@1":
                raise ValueError("an invented refusal of the chain")
            return real(db, row)

        with mock.patch.object(F, "append_registry", picky):
            out = h.sync()
        self.assertEqual((out["registered"], out["skipped"]), (1, [{"key": "alpha@1", "why": R.CAUSES["row"]}]))
        self.assertEqual(h.keys(), ["beta@1"])


class TheJob(unittest.TestCase):
    def ctx(self, h: House, **swarm_json) -> Context:
        (h.root / "swarm.json").write_text(json.dumps(swarm_json))
        return Context("forward_register", root=h.root, due_at=h.clock(), clock=h.clock, config={}, settings_value={})

    def record(self, **forward) -> dict:
        return {"elane": {"universe": list(UNIVERSE), "forward": {"mode": "record", "controls_per_group": 2, **forward}}}

    def test_it_is_off_until_the_switch_says_record(self):
        h = House(self)
        h.family("alpha", {1: FAILED})
        for swarm_json in ({}, {"elane": {"forward": {"mode": "off"}}}, {"elane": {"forward": {"mode": "rank"}}},
                           {"elane": {"mode": "gate"}}):
            ctx = self.ctx(h, **swarm_json)
            with mock.patch("league.swarm.settings.read_policy", return_value=({}, {"state": "ok"})):
                self.assertEqual(R.run(ctx), {"status": "skipped", "why": "elane.forward.mode is off"}, swarm_json)
            self.assertEqual(ctx.alerts, [])
        self.assertEqual(F.verify_chain(h.db)["rows"], 0)

    def test_no_swarm_store_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "swarm.json").write_text(json.dumps(self.record()))
            ctx = Context("forward_register", root=tmp, due_at=1.0, clock=lambda: at(F.t0(), 10), config={},
                          settings_value={})
            self.assertEqual(R.run(ctx), {"status": "skipped", "why": "no swarm store: nothing to register"})
            self.assertFalse((Path(tmp) / F.DB).exists(), "a skipped run creates no store")

    def test_the_receipt_holds_counts_the_chain_and_its_head(self):
        h = House(self)
        a = h.family("alpha", {1: PASSED}, passed_version=1)
        h.family("beta", {1: UNJUDGED["RUN"]})
        ctx = self.ctx(h, **self.record())
        receipt = R.run(ctx)
        self.assertEqual(receipt, {"ok": True, "registered": 1, "controls": 2, "tagged": 1, "stopped": 0, "suspect": 0,
                                   "skipped": 0, "rows": 3, "chain_ok": True, "head": F.head(h.db),
                                   "identity_moved": False})
        self.assertEqual(ctx.alerts, [])
        self.assertEqual(h.row(f"{a}@1")["registered_at"], h.clock())
        again = R.run(self.ctx(h, **self.record()))
        self.assertEqual({k: again[k] for k in ("registered", "controls", "tagged", "rows", "head")},
                         {"registered": 0, "controls": 0, "tagged": 0, "rows": 3, "head": receipt["head"]})
        json.dumps(receipt)

    def test_a_broken_chain_is_a_house_warning(self):
        h = House(self)
        h.family("alpha", {1: PASSED})
        R.run(self.ctx(h, **self.record()))
        h.db.execute("DROP TRIGGER fwd_registry_no_update")
        h.db.execute("UPDATE fwd_registry SET alpha_f='0.12' WHERE pid=1")
        h.db.commit()
        ctx = self.ctx(h, **self.record())
        receipt = R.run(ctx)
        self.assertEqual((receipt["ok"], receipt["chain_ok"]), (False, False))
        (alert,) = ctx.alerts
        self.assertEqual(alert["level"], "warning")
        self.assertIn("FW4", alert["text"])
        self.assertIn("pid 1 of 3 rows", alert["text"])
        self.assertNotRegex(alert["text"], FIGURE)

    def test_a_store_that_cannot_be_read_is_a_failed_receipt(self):
        h = House(self)
        h.family("alpha", {1: PASSED})
        (h.root / R.LIVE_DB).write_bytes(b"this is not a database, " * 50)
        receipt = R.run(self.ctx(h, **self.record()))
        self.assertEqual((receipt["status"], receipt["ok"], receipt["registered"], receipt["skipped"]),
                         ("failed", False, 1, 0))
        self.assertIn(R.LIVE_DB, receipt["error"])
        self.assertNotRegex(receipt["error"], FIGURE)

    def test_the_identity_watch(self):
        h = House(self)
        fid = h.family("alpha", {1: PASSED})
        from league.swarm import evaluator

        def run(fingerprint: str) -> tuple[dict, list]:
            ctx = self.ctx(h, **self.record())
            with mock.patch.object(evaluator, "equity_fingerprint", lambda: fingerprint):
                return R.run(ctx), ctx.alerts

        receipt, alerts = run("a" * 64)
        self.assertEqual((receipt["identity_moved"], alerts, F.kv_get(h.db, "equity_sha")), (False, [], "a" * 64),
                         "the first sighting only records it")
        receipt, alerts = run("b" * 64)
        self.assertEqual((receipt["identity_moved"], alerts, F.kv_get(h.db, "equity_sha")), (True, [], "b" * 64),
                         "a move with no live instance is no alarm")
        self.assertEqual(F.events(h.db, "identity_moved"), [])
        h.book(h.instance(fid, 1), h.instance(fid, 1, id="old@1:r", retired_at=5.0))
        receipt, alerts = run("c" * 64)
        self.assertTrue(receipt["identity_moved"])
        (alert,) = alerts
        self.assertEqual(alert["level"], "warning")
        self.assertIn("FW8", alert["text"])
        self.assertIn("1 equity instances are live", alert["text"])
        self.assertIn("b" * 12 + " to " + "c" * 12, alert["text"])
        self.assertNotRegex(alert["text"], FIGURE)
        (event,) = F.events(h.db, "identity_moved")
        self.assertEqual(event["payload"], {"was": "b" * 12, "now": "c" * 12, "live": 1, "once": "c" * 64,
                                            "why": "the equity evidence identity moved while a lineage is live"})
        receipt, alerts = run("c" * 64)
        self.assertEqual((receipt["identity_moved"], alerts), (False, []), "the kv holds the new value: said once")
        # A release that moves it back to a value already seen: one event a value, and no second alert for it.
        run("b" * 64)
        receipt, alerts = run("c" * 64)
        self.assertEqual((len(F.events(h.db, "identity_moved")), alerts), (2, []))

    def test_the_alert_texts_hold_ids_counts_and_dates_only(self):
        self.assertRegex("a return of 0.012", FIGURE)
        self.assertRegex("15 bp a side", FIGURE)
        self.assertRegex("95% of sessions", FIGURE)
        self.assertNotRegex("pid 12 of 340 rows on 2026-10-13 (FW4), sha 0f3a9c", FIGURE)


if __name__ == "__main__":
    unittest.main()
