#!/usr/bin/env python3
"""The nightly forward job: yesterday's market into the data box's store and the gate image only.

    python3 scripts/data/nightly.py run [--day YYYY-MM-DD] [--dry-run]
    python3 scripts/data/nightly.py schedule        sleep the data box until the next 02:00 ET wake
    python3 scripts/data/nightly.py status
    python3 scripts/data/nightly.py daemon --state /workspace/state/data \
        --ready-file /workspace/state/gym-forward.json

`run` (idempotent; each step checks what is already done, so a rerun after any failure finishes
the night and a second run of a finished night does nothing):
  1. the day: the last trading day before today (ET), which must be a forward day (after the
     holdout's 2026-09-25) and at least 01:45 ET behind us (ThetaData serves the previous day from
     then);
  2. the data box: woken; the backfill stopped if it is running (ThetaData allows one session per
     account); `backfill.py run --stages 7 --forward-days DAY` pulls the day for the whole universe,
     then `--stages 8` its SPY/QQQ back months (resumable: a root already in the journal is not
     fetched again); the backfill restarted with its last arguments;
  3. the gate image: its box woken (or, when it is gone, forked from its current checkpoint and sealed
     again), each of the day's files downloaded from the data box and uploaded to the same path,
     `backfill.py adopt` there checks every sha256 and journals them, and the gate is re-checkpointed
     with a one-year TTL; the new checkpoint becomes `gate.current_checkpoint` in images.json;
  4. both boxes back to sleep (the data box only when no backfill runs), the data box with a wake
     at the next trading night's 02:00 ET (06:00Z in summer, 07:00Z in winter).

Forward days go to the gate image and never to a Gym box: the Gym image's box id is refused as a
target. The House supervises `daemon` after the operator installs the private data records and
enables it. The daemon catches up missing forward days, retries failures, and atomically publishes
a checkpoint-ready manifest for the swarm. Its first due time is Tuesday 2026-09-29 06:00Z.

THE CHAIN'S RULE (Oct 1, 2026). The chain names the gate image it extends: each day's record and the ready file carry
`base_checkpoint` (images.json's `gate.current` first checkpoint) and `holdout_roots` (the roots that image was built
with), and the swarm takes the ready checkpoint only when they are the gate `swarm.json` names and cover its roots
(league/swarm/settings.py `ready_refusal`). `run` (and the daemon) refuses, before any box is woken (`preflight`), to
extend a gate image that does not list its roots or lacks one of the swarm's `gym.roots` (`--swarm-root`, by default
the state directory's parent; the daemon's is its ready file's folder), or a chain whose tip is not proven on that image
(`settings.chain_refusal`: the chain records were not reset when the image was adopted). `stamp-ready` names the gate
image in a ready file written before the release that added these fields. Sept 29-30: the chain extended the five-root
image while `swarm.json` named the 25-root one, and its ready file replaced it.

THE SOURCE GAP (Oct 14, 2026). The night stays strict for a root whose SIP bars may still arrive (scripts/data/sip.py).
Each failed relay records, with the day (`forward_days[day].sip_watch`), every short root's packet and since when the
source has served it unchanged; a changed packet restarts that root's clock. Only a small gap is a source gap: bars
served and at most `SOURCE_GAP_MAX_MINUTES` (5) minutes missing, on at most `SOURCE_GAP_MAX_ROOTS` (2) roots of the
day; an empty or invalid packet, a wider gap or more short roots is an outage whose bars may come later, so the day
stays held and the stall alarm's owed-day step goes to the owner. Within the bound, a root whose packet has stood
unchanged for `SOURCE_SETTLE` (6 h) and past the close of the next session (at most `SOURCE_SETTLE_CAP`, 24 h: a
Friday's gap waits a day, not the weekend) is handed to the forward gap ledger (`forward_days[day].sip_gaps`): the relay
ingests the day's complete roots and leaves that root's packet quarantined, the SIP proof names it `source_incomplete`
(never complete), the day is copied and checkpointed with the root's own canonical file (the vendor's option-implied
series, labeled with its source in the journal; nothing is filled), and the ready file says so (`sip_coverage.status`
and the chain's `source_incomplete` list). The controller records how long it has retried a day (`nightly.json`
`retrying`) for the stall alarm (`league/ops/stall.py` `forward`). Oct 12-14: SLV 389/390 (minute 826 never served) held
every later day.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storelib as sl  # noqa: E402

FIRST_FORWARD_DAY = dt.date(2026, 9, 28)
READY_ET_MINUTES = 105  # 01:45 ET
QUIET_EXIT = sl.QUIET_EXIT  # a `--nightly-quiet` backfill that the quiet window deferred
#: THE SOURCE GAP (the module docstring): how long a short root's SIP packet must stand unchanged across retries before it
#: is handed to the forward gap ledger, and the most it waits for the next session's close.
SOURCE_SETTLE = 6 * 3600
SOURCE_SETTLE_CAP = 24 * 3600
#: Only a small gap is a source gap: a root with bars short by at most this many regular-session minutes (status
#: "partial"), and at most this many short roots on the day. An empty or invalid packet, a wider gap or more short
#: roots is an outage (the bars may come later): the day stays held, no hand-off is scheduled, and the stall alarm's
#: owed-day step goes to the owner (league/ops/stall.py `forward`).
SOURCE_GAP_MAX_MINUTES = 5
SOURCE_GAP_MAX_ROOTS = 2
#: The fields of a SIP receipt the forward gap ledger keeps (no price: coverage, identities and the quarantine path).
GAP_FIELDS = ("root", "day", "known", "expected", "missing_minutes", "packet_sha256", "source_symbol", "quarantine")

BACKFILL_IDENTITY = r'''
import os, pathlib
def identity(pid, proc_root='/proc'):
    try:
        base = pathlib.Path(proc_root) / str(pid)
        stat = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        argv = (base / 'cmdline').read_bytes().decode().split('\0')
        cwd = (base / 'cwd').resolve()
        exact = any(pathlib.Path(arg).name == 'backfill.py' and argv[i+1] == 'run'
                    and (cwd / arg).resolve() == pathlib.Path('/data/code/backfill.py')
                    for i, arg in enumerate(argv[:-1]))
        return (stat[19], int(stat[2])) if exact else None
    except (OSError, ValueError, IndexError, UnicodeError):
        return None
'''


def eastern(now: dt.datetime) -> dt.datetime:
    from zoneinfo import ZoneInfo

    return now.astimezone(ZoneInfo("America/New_York"))


def target_day(now: dt.datetime, calendar: sl.Calendar) -> dt.date:
    """The previous trading day, if ThetaData has published it; ValueError otherwise."""
    local = eastern(now)
    if local.hour * 60 + local.minute < READY_ET_MINUTES:
        raise ValueError(f"it is {local:%H:%M} ET: the previous day is served from 01:45 ET")
    return calendar.previous(local.date())


def next_wake(now: dt.datetime, calendar: sl.Calendar) -> dt.datetime:
    """02:00 America/New_York after a trading day; 06:00Z in summer, 07:00Z in winter."""
    day = eastern(now).date()
    while True:
        candidate = scheduled_at(day)
        if candidate > now and day > FIRST_FORWARD_DAY and calendar.is_trading(day - dt.timedelta(days=1)):
            return candidate
        day += dt.timedelta(days=1)


def scheduled_at(morning: dt.date, minute: int = 120) -> dt.datetime:
    from zoneinfo import ZoneInfo

    return dt.datetime.combine(morning, dt.time(minute // 60, minute % 60),
                               ZoneInfo("America/New_York")).astimezone(dt.timezone.utc)


def due_days(now: dt.datetime, calendar: sl.Calendar, finished: Sequence[str] = ()) -> list[dt.date]:
    """All missing forward sessions already due, oldest first (also recovers an outage)."""
    return [day for day in calendar.days(FIRST_FORWARD_DAY, eastern(now).date() - dt.timedelta(days=1))
            if day.isoformat() not in finished and scheduled_at(day + dt.timedelta(days=1)) <= now]


def next_session_close(day: dt.date, calendar: sl.Calendar) -> dt.datetime:
    """The close (UTC) of the first session after `day`."""
    after = day + dt.timedelta(days=1)
    while not calendar.is_trading(after):
        after += dt.timedelta(days=1)
    return scheduled_at(after, calendar.hours(after)[1])


def small_gap(row: Mapping[str, Any]) -> bool:
    """THE SOURCE GAP's bound for one short root's SIP receipt: bars served ("partial") and at most
    `SOURCE_GAP_MAX_MINUTES` regular-session minutes missing."""
    known, expected = row.get("known"), row.get("expected")
    return (row.get("status") == "partial" and isinstance(known, int) and isinstance(expected, int)
            and not isinstance(known, bool) and 0 < expected - known <= SOURCE_GAP_MAX_MINUTES)


def source_gap(state: Mapping[str, Any]) -> bool:
    """Whether the day's short roots (`sip_watch`, with any the ledger holds) are a source gap the House may hand off by
    itself: each `small_gap`, and at most `SOURCE_GAP_MAX_ROOTS` of them. Anything wider stays strict for the owner."""
    watch = state.get("sip_watch") or {}
    roots = set(watch) | set(state.get("sip_gaps") or {})
    return bool(watch) and len(roots) <= SOURCE_GAP_MAX_ROOTS and all(small_gap(row) for row in watch.values())


def handoff_at(day: dt.date, first_seen: dt.datetime, calendar: sl.Calendar) -> dt.datetime:
    """THE SOURCE GAP: when a root of `day` whose packet the source has served unchanged since `first_seen` may be handed
    to the forward gap ledger: `SOURCE_SETTLE` after it, and not before the next session's close, but never later than
    `SOURCE_SETTLE_CAP` after it."""
    settle = first_seen + dt.timedelta(seconds=SOURCE_SETTLE)
    return max(settle, min(next_session_close(day, calendar), first_seen + dt.timedelta(seconds=SOURCE_SETTLE_CAP)))


class Nightly:
    """The job over two box handles and a record store; every dependency is injected for tests.

    `data` and `gate` are objects with: status() -> str; wake(); sleep(wake_at: str | None);
    run(args: str, timeout: int) -> (ok: bool, stdout: str); download(path) -> bytes;
    upload(path, bytes, mode). `images` is a dict-like record (images.json), saved with `save()`.
    `checkpoint(box_id) -> id` checkpoints the gate. `backfill` holds the last backfill args.
    """

    def __init__(self, *, data: Any, gate: Any, images: dict[str, Any], save: Callable[[dict[str, Any]], None],
                 checkpoint: Callable[[], str], calendar: sl.Calendar, last_backfill_args: str | None,
                 gym_box_ids: Sequence[str] = (), log: Callable[[str], None] = print,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc), rehearsal: bool = False,
                 relay: Callable[[dt.date, Any], None] | None = None,
                 sip_check: Callable[[dt.date, Any], dict] | None = None,
                 check_lease: Callable[[], None] = lambda: None):
        self.data, self.gate, self.images, self.save = data, gate, images, save
        self.checkpoint = checkpoint
        self.calendar = calendar
        self.last_backfill_args = last_backfill_args
        self.gym_box_ids = set(gym_box_ids)
        self.log = log
        self.clock = clock
        #: A rehearsal copies a day the data box already holds (a holdout day) to a rehearsal gate box,
        #: skips the pull, and records under `nightly_rehearsals`, never as the gate's state.
        self.rehearsal = rehearsal
        self.relay = relay
        self.sip_check = sip_check
        self.check_lease = check_lease

    def persist(self) -> None:
        self.check_lease()
        self.save(self.images)

    def gate_identity(self) -> dict[str, Any]:
        """The gate image this chain extends (images.json's `gate.current`): its first checkpoint and the roots its holdout
        was built with (None when the record lists none). Recorded with each day's checkpoint and published in the ready
        file, so the swarm takes the chain only while it extends the gate `swarm.json` names (THE CHAIN'S RULE,
        `league/swarm/settings.py` `ready_refusal`)."""
        current = (self.images.get("gate") or {}).get("current") or {}
        roots = current.get("roots")
        return {"base_checkpoint": (current.get("checkpoints") or [None])[0],
                "holdout_roots": sorted({str(r).upper() for r in roots}) if isinstance(roots, list) else None}

    def proven_identity(self, checkpoint: str) -> dict[str, Any]:
        """`gate_identity()` for a checkpoint recorded without one (by a release before Oct 1, 2026) when the chain's
        records prove it extends the current gate image (`settings.chain_refusal`); nothing otherwise, and the day is then
        completed but not published (`publish_ready`)."""
        import boxlib  # noqa: F401 - puts the repository on sys.path
        from league.swarm import settings as swarm_settings

        try:
            proven = swarm_settings.chain_refusal(self.images.get("gate") or {}, checkpoint) is None
        except Exception:  # noqa: BLE001 - unreadable records prove nothing
            proven = False
        return self.gate_identity() if proven else {}

    def state(self, day: dt.date) -> dict[str, Any]:
        if self.rehearsal:
            key = f"{day.isoformat()}:{self.gate.box_id}"
            return self.images.setdefault("nightly_rehearsals", {}).setdefault(key, {})
        nights = self.images.setdefault("gate", {}).setdefault("forward_days", {})
        return nights.setdefault(day.isoformat(), {})

    def chain_gaps(self, upto: dt.date, base: Any) -> list[dict[str, Any]]:
        """THE SOURCE GAP: every root-day the forward gap ledger holds on this chain (checkpointed days up to `upto` that
        name the same gate image), for the ready file: whatever reads the publication sees each one, not only today's."""
        out = []
        for day, night in sorted(((self.images.get("gate") or {}).get("forward_days") or {}).items()):
            if day > upto.isoformat() or not night.get("checkpoint") or night.get("base_checkpoint") != base:
                continue
            for root, gap in sorted((night.get("sip_gaps") or {}).items()):
                out.append({"day": day, "root": root, "status": "source_incomplete", "complete": False,
                            **{k: gap.get(k) for k in ("known", "expected", "missing_minutes", "packet_sha256",
                                                       "unchanged_since", "handed_off_at")}})
        return out

    def watch_gaps(self, day: dt.date, state: dict[str, Any], gaps: Sequence[Mapping[str, Any]]) -> None:
        """THE SOURCE GAP's retry clock (`sip_watch`, durable with the day): each short root's packet and since when the
        source has served it unchanged. A changed packet (bars still arriving) restarts its clock and takes it out of the
        ledger; a root no longer short leaves the watch."""
        now = self.clock().isoformat()
        prior, ledger = state.get("sip_watch") or {}, state.get("sip_gaps") or {}
        watch = {}
        for row in gaps:
            root, sha = str(row.get("root")), row.get("packet_sha256")
            last = prior.get(root) or {}
            same = bool(sha) and last.get("packet_sha256") == sha
            watch[root] = {**{k: row.get(k) for k in GAP_FIELDS}, "status": row.get("status"),
                           "first_seen": last.get("first_seen") if same else now, "last_seen": now,
                           "attempts": int(last.get("attempts") or 0) + 1 if same else 1}
            if root in ledger and ledger[root].get("packet_sha256") != sha:
                ledger.pop(root)
        state["sip_watch"] = watch
        if "sip_gaps" in state and not ledger:
            state.pop("sip_gaps")

    def handoff(self, day: dt.date, state: Mapping[str, Any]) -> dict[str, str]:
        """The roots this run may hand to the forward gap ledger ({root: the exact packet}): those it already holds,
        and, when the day's short roots are a `source_gap` (small, few), each watched root whose packet has stood
        unchanged until `handoff_at`. A wider gap (an outage) hands nothing new: the day stays strict."""
        now = self.clock()
        out = {root: gap["packet_sha256"] for root, gap in (state.get("sip_gaps") or {}).items() if gap.get("packet_sha256")}
        if not source_gap(state):
            return out
        for root, row in (state.get("sip_watch") or {}).items():
            try:
                first = dt.datetime.fromisoformat(str(row["first_seen"]))
            except (KeyError, TypeError, ValueError):
                continue
            if row.get("packet_sha256") and now >= handoff_at(day, first, self.calendar):
                out.setdefault(root, row["packet_sha256"])
        return out

    def relay_sip(self, day: dt.date, state: dict[str, Any]) -> Any:
        """The day's SIP relay under THE SOURCE GAP: strict, but for the roots `handoff` names (for their exact packets)."""
        handed = self.handoff(day, state)
        try:
            result = self.relay(day, self.data, source_incomplete=handed) if handed else self.relay(day, self.data)
        except Exception as error:
            gaps = getattr(error, "coverage", None)
            if isinstance(gaps, list) and gaps and all(isinstance(g, Mapping) for g in gaps):
                self.watch_gaps(day, state, gaps)
                self.persist()
                # When the day can go on if every short packet stays as it is (the controller's `retrying`, the stall
                # alarm's scheduled way out); None for a gap too wide to hand off, so the owed day's step is not held.
                error.handoff_at = (max(handoff_at(day, dt.datetime.fromisoformat(w["first_seen"]), self.calendar)
                                        for w in state["sip_watch"].values()).isoformat()
                                    if source_gap(state) else None)
            raise
        result_map = result if isinstance(result, Mapping) else {}
        short = set(result_map.get("source_incomplete") or [])
        watch, before = state.pop("sip_watch", None) or {}, state.get("sip_gaps") or {}
        ledger = {}
        for row in (result_map.get("coverage") or []) if short else []:
            root = row.get("root")
            if root in short:
                seen, held = watch.get(root) or {}, before.get(root) or {}
                ledger[root] = {**{k: row.get(k) for k in GAP_FIELDS}, "status": "source_incomplete", "complete": False,
                                "source_status": row.get("status"),
                                "unchanged_since": held.get("unchanged_since") or seen.get("first_seen"),
                                "attempts": seen.get("attempts") or held.get("attempts"),
                                "handed_off_at": held.get("handed_off_at") or self.clock().isoformat()}
        if ledger:
            state["sip_gaps"] = ledger
            self.log(f"{day}: SIP source-incomplete, handed to the forward gap ledger: "
                     + ", ".join(f"{r} {g['known']}/{g['expected']}" for r, g in sorted(ledger.items())))
        else:
            state.pop("sip_gaps", None)
        return result

    def run(self, day: dt.date | None = None, *, dry_run: bool = False) -> dict[str, Any]:
        now = self.clock()
        day = day or target_day(now, self.calendar)
        if sl.window_of(day) != "forward" and not (self.rehearsal and sl.window_of(day) == "holdout"):
            raise ValueError(f"{day} is {sl.window_of(day)}, not a forward day")
        if not self.calendar.is_trading(day):
            return {"day": day.isoformat(), "skipped": "not a trading day"}
        if not self.rehearsal and now < scheduled_at(day + dt.timedelta(days=1), READY_ET_MINUTES):
            raise ValueError(f"{day} has not been published yet (01:45 ET on the following day)")
        if getattr(self.gate, "box_id", None) in self.gym_box_ids:
            raise ValueError("the gate target is a Gym box: forward days never reach a Gym box")
        state = self.state(day)
        self.check_lease()
        if state.get("checkpoint"):
            self.log(f"{day}: already done (gate checkpoint {state['checkpoint']})")
            done = {"day": day.isoformat(), "already": True, 'sip_coverage': {'status': 'legacy_unverified'}, **state}
            if not self.rehearsal and not state.get("base_checkpoint"):
                done.update(self.proven_identity(state["checkpoint"]))  # a day an earlier release checkpointed
            if not self.rehearsal:
                done["source_incomplete"] = self.chain_gaps(day, done.get("base_checkpoint"))
            return done
        if dry_run:
            return {"day": day.isoformat(), "would": ["pull", "copy", "checkpoint"]}

        # 1. the pull, on the data box, with the backfill paused (one ThetaData session per account)
        self.data.wake()
        need_pull = not state.get("pulled") and not self.rehearsal
        was_running = need_pull and self.data.backfill_running()
        if was_running:
            if not self.last_backfill_args:
                raise RuntimeError("cannot pause a running backfill without its restart arguments")
            state["resume_backfill"] = self.last_backfill_args
            self.persist()
            self.check_lease()
            self.data.stop_backfill()
        try:
            if need_pull:
                for stage in (7, 8):  # the day's chains, then (needing them) the back months
                    self.check_lease()
                    ok, out = self.data.run(f"backfill.py run --stages {stage} --forward-days {day.isoformat()} "
                                            "--threads 8 --passes 3 --pause 120", timeout=1800)
                    if not ok:
                        raise RuntimeError(f"the forward pull (stage {stage}) failed: {out[-800:]}")
                if self.relay:
                    self.check_lease()
                    self.relay_sip(day, state)
                state["pulled"] = self.clock().isoformat()
                self.persist()
            ok, out = self.data.run(f"backfill.py records --date {day.isoformat()}", timeout=600)
            if not ok:
                raise RuntimeError(f"no records for {day}: {out[-400:]}")
            records = [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]
        finally:
            if state.get("resume_backfill") and not self.data.backfill_running():
                self.check_lease()
                self.data.start_backfill(state["resume_backfill"])
                state.pop("resume_backfill")
                self.persist()
        files = [r for r in records if r.get("type") == "file"]
        if not files:
            raise RuntimeError(f"the data box holds no files for {day}")
        allowed = ("forward", "holdout") if self.rehearsal else ("forward",)
        if any(r.get("window") not in allowed for r in files):
            raise RuntimeError("a record that is not a forward day was about to reach the gate")
        for record in files:
            parsed = sl.parse_rel_path(record.get("path", ""))
            if (parsed is None or record.get("path") != sl.rel_path(*parsed) or parsed[2] != day
                    or parsed != (record.get("kind"), record.get("root"), day)
                    or record.get("date") != day.isoformat()):
                raise RuntimeError("invalid or mismatched path in forward records")
        kinds = {}
        for record in files:
            kinds.setdefault(record["root"], set()).add(record["kind"])
        if any("nbbo" in present and "underlying" not in present for present in kinds.values()):
            state.pop("pulled", None)
            self.persist()
            raise RuntimeError("the forward day has NBBO without its underlying series")
        if self.sip_check and not self.rehearsal:
            # A legacy/resumed 'pulled' marker is not a receipt. Bind fresh verification to the
            # exact transferred records, never just another view of the mutable source box.
            try:
                self.check_lease()
                ledger = state.get('sip_gaps') or {}
                proof = (self.sip_check(day, self.data, source_incomplete=sorted(ledger)) if ledger
                         else self.sip_check(day, self.data))
                roots = sorted(r for r, present in kinds.items() if 'nbbo' in present and r not in ('XSP', 'SPXW'))
                pairs = sorted((r['root'], r['sha256']) for r in files if r['kind'] == 'underlying' and r['root'] in roots)
                digest = hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest()
                rows = proof.get('source_incomplete') or []
                short = sorted(str(r.get('root')) for r in rows if isinstance(r, Mapping))
                # THE SOURCE GAP: short roots only as the ledger holds them, each said, never a complete claim.
                status_ok = ((proof.get('status') == 'complete' and not rows) or
                             (proof.get('status') == 'source_incomplete' and bool(short) and len(short) == len(rows)
                              and len(set(short)) == len(short) and set(short) <= set(ledger)))
                if (proof.get('schema') != sl.SIP_COVERAGE_SCHEMA or not status_ok
                        or proof.get('day') != str(day) or proof.get('roots') != roots or len(pairs) != len(roots)
                        or proof.get('files_sha256') != digest):
                    raise RuntimeError('forward SIP proof differs from the exact files to be copied')
                if short:
                    proof = {**proof, 'source_incomplete': [{**row, **ledger[row['root']], 'canonical_status': row.get('status')}
                                                            for row in rows]}
                state['sip_coverage'] = proof
            except Exception:
                state.pop('pulled', None)
                state.pop('sip_coverage', None)
                self.persist()
                raise

        # 2. the copy, file by file, checked on arrival
        self.gate.wake()
        copied = 0
        for record in files:
            self.check_lease()
            blob = self.data.download(f"{sl.STORE_ROOT}/{record['path']}")
            if hashlib.sha256(blob).hexdigest() != record["sha256"]:
                raise RuntimeError(f"{record['path']} changed on the way (sha256)")
            self.gate.upload(f"{sl.STORE_ROOT}/{record['path']}", blob, 0o644)
            copied += 1
        payload = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode()
        records_path = f"/data/work/nightly-{day.isoformat()}.jsonl"
        self.check_lease()
        self.gate.upload(records_path, payload, 0o644)
        ok, out = self.gate.run(f"backfill.py adopt --records {records_path}", timeout=1800)
        if not ok:
            raise RuntimeError(f"the gate refused the day: {out[-800:]}")
        state.update({"files": copied, "adopted": self.clock().isoformat(), "roots": sorted({r['root'] for r in files})})
        self.persist()

        # 3. the gate's new checkpoint
        self.check_lease()
        checkpoint = self.checkpoint()
        self.check_lease()
        state["checkpoint"] = checkpoint
        if not self.rehearsal:
            identity = self.gate_identity()
            state.update(identity)
            gate = self.images.setdefault("gate", {})
            gate["current_checkpoint"] = checkpoint
            gate.setdefault("checkpoints", []).append({"id": checkpoint, "day": day.isoformat(), "at": self.clock().isoformat(),
                                                       "base": identity["base_checkpoint"]})
        self.persist()
        self.gate.sleep(None)
        if not self.data.backfill_running():
            self.data.sleep(next_wake(self.clock(), self.calendar).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.log(f"{day}: {copied} files to the gate; checkpoint {checkpoint}")
        result = {"day": day.isoformat(), **state}
        if not self.rehearsal:
            result["source_incomplete"] = self.chain_gaps(day, state.get("base_checkpoint"))
        return result


# ------------------------------------------------------------------------------ the real handles
class BoxHandle:
    def __init__(self, api: Any, box_id: str, *, defer_sleep: bool = False):
        self.api, self.box_id = api, box_id
        self.defer_sleep = defer_sleep
        self.pending_sleep = False
        self.wake_at = None

    def status(self) -> str:
        return str((self.api.get(self.box_id) or {}).get("status") or "")

    def wake(self) -> None:
        import boxlib as bl

        bl.ensure_running(self.api, self.box_id)

    def sleep(self, wake_at: str | None) -> None:
        if self.defer_sleep:
            self.pending_sleep, self.wake_at = True, wake_at
        else:
            self.api.sleep(self.box_id, wake_at=wake_at)

    def flush_sleep(self) -> None:
        if self.pending_sleep:
            self.api.sleep(self.box_id, wake_at=self.wake_at)
            self.pending_sleep = False

    def run(self, args: str, timeout: int) -> tuple[bool, str]:
        import boxlib as bl

        result = bl.run_py(self.api, self.box_id, args, timeout=timeout)
        return result.ok, result.stdout if result.ok else result.output

    def download(self, path: str) -> bytes:
        return self.api.download(self.box_id, path, timeout=900)

    def upload(self, path: str, blob: bytes, mode: int) -> None:
        self.api.upload(self.box_id, path, blob, mode=mode, timeout=900)

    def backfill_running(self) -> bool:
        code = BACKFILL_IDENTITY + """
p = pathlib.Path('/data/work/backfill.pid')
try:
    pid = int(p.read_text())
    print('yes' if identity(pid) is not None else 'no')
except (OSError, ValueError):
    print('no')
"""
        out = self.api.exec(self.box_id, ["/opt/data-venv/bin/python", "-c", code], timeout=60)
        if not out.ok:
            raise RuntimeError("could not read the backfill process state")
        return out.stdout.strip() == "yes"

    def stop_backfill(self) -> None:
        code = BACKFILL_IDENTITY + """
import signal, time
try:
    pid = int(pathlib.Path('/data/work/backfill.pid').read_text())
except (OSError, ValueError):
    raise SystemExit(0)
initial = identity(pid)
def alive():
    return initial is not None and identity(pid) == initial
if initial is not None:
    def send(sig):
        # Re-check start ticks, exact script path/argv and group ownership before EVERY signal.
        if not alive():
            return
        try:
            os.killpg(pid, sig) if initial[1] == pid else os.kill(pid, sig)
        except ProcessLookupError:
            pass
    send(signal.SIGTERM)
    for _ in range(60):
        if not alive(): break
        time.sleep(1)
    if alive(): send(signal.SIGKILL)
    for _ in range(10):
        if not alive(): break
        time.sleep(1)
    if alive(): raise SystemExit('backfill did not stop')
if identity(pid) is not None:
    raise SystemExit('backfill identity changed during stop; retry under the operation lease')
"""
        self.api.exec(self.box_id, ["/opt/data-venv/bin/python", "-c", code], timeout=90).check()

    def start_backfill(self, args: str) -> str:
        """Start `backfill.py run ARGS` detached; returns the path of its exit-status receipt. A run that exits 0 (an
        empty queue) or 75 (`--nightly-quiet` inside the quiet window: deferred, no login) is not an error."""
        import boxlib as bl

        if self.backfill_running():
            raise RuntimeError("refusing to start a second backfill session")
        receipt = f"/data/work/restart-{uuid.uuid4().hex}.exit"
        run = shlex.join([bl.VENV_PY, "backfill.py", "run", *shlex.split(args)])
        inner = f"{run}; status=$?; echo $status > {shlex.quote(receipt)}; exit $status"
        command = (f"mkdir -p /data/work && cd {shlex.quote(bl.CODE_DIR)} && setsid nohup sh -c {shlex.quote(inner)} "
                   ">> /data/work/backfill.out 2>&1 < /dev/null &")
        self.api.exec(self.box_id, command, timeout=60, background=True).check()
        for _ in range(20):
            if self.backfill_running():
                return receipt
            code = self.receipt(receipt)
            if code is not None:
                if code in (0, QUIET_EXIT):
                    return receipt  # the resumable queue was already empty, or the quiet window defers it
                raise RuntimeError(f"the backfill restart exited with {code}")
            time.sleep(0.5)
        raise RuntimeError("the restarted backfill never confirmed its running identity or a clean completion")

    def receipt(self, path: str) -> int | None:
        """A started backfill's exit status (None while it runs, or if it left none)."""
        result = self.api.exec(self.box_id, ["bash", "-c", f"cat {shlex.quote(path)} 2>/dev/null || true"], timeout=60)
        text = result.stdout.strip()
        try:
            return int(text) if text else None
        except ValueError:
            return None


def swarm_roots(swarm_root: Path | None) -> list[str]:
    """The swarm's `gym.roots` (league/swarm/settings.py: config.json, then `<swarm_root>/swarm.json`): every root a holdout
    look may need. The House's swarm root is the parent of this state directory (`<root>/data`)."""
    import boxlib as bl  # noqa: F401 - puts the repository on sys.path
    from league.swarm import settings as swarm_settings

    roots = (swarm_settings.load(swarm_root)["gym"] or {}).get("roots") or []
    return sorted({str(r).upper() for r in roots})


def gate_holdout_gap(gate: Mapping[str, Any], required: Sequence[str]) -> str | None:
    """Why the nightly may not extend the gate image `gate` (images.json's `gate.current`) for a swarm whose `gym.roots`
    are `required`, or None when it may: its recorded roots (`roots`, the list it was built with) must cover them. A gate
    recorded without a list ("all", or none: `images.py finish` writes none) cannot show it holds them and is refused."""
    held = gate.get("roots")
    name = gate.get("version") or (gate.get("checkpoints") or ["?"])[0]
    if not isinstance(held, list):
        return (f"the gate image {name} does not list the roots it holds ({held!r}); the swarm's roots are "
                f"{', '.join(required)}. Point images.json's gate at the image swarm.json names (gym.gate_checkpoint)")
    lacking = sorted({str(r).upper() for r in required} - {str(r).upper() for r in held})
    if lacking:
        return (f"the gate image {name} holds no holdout for {', '.join(lacking)} (gym.roots); point images.json's gate at "
                "the image swarm.json names (gym.gate_checkpoint)")
    return None


def preflight(images: Mapping[str, Any], swarm_root: Path | None = None) -> None:
    """THE CHAIN'S RULE, before any box is woken: raises unless the nightly may extend the gate image images.json records
    (`images`): one is recorded, it holds a holdout for every root of the swarm (`gate_holdout_gap`, `gym.roots` under
    `swarm_root`, by default this state directory's parent), and the chain's tip (`current_checkpoint`) is proven on it
    (`settings.chain_refusal`; a tip on another image means the chain records were not reset when the image was
    adopted, and a re-fork from it would carry another image's holdout under this one's name)."""
    import boxlib as bl
    from league.swarm import settings as swarm_settings

    record = images.get("gate") or {}
    gate = record.get("current") or {}
    if not gate.get("box_id"):
        raise RuntimeError("no gate image recorded in images.json; build it first (images.py build gate)")
    problem = gate_holdout_gap(gate, swarm_roots(swarm_root if swarm_root is not None else bl.STATE_DIR.parent))
    if problem:
        raise RuntimeError(f"refused to extend the gate: {problem}")
    tip = record.get("current_checkpoint")
    lineage = swarm_settings.chain_refusal(record, tip) if tip else None
    if lineage:
        raise RuntimeError(f"refused to extend the gate: its chain's tip {tip} is not proven on the gate image ({lineage}). "
                           "Reset the chain records to the image (docs/operations.md, the chain's rule)")


def real_job(*, rehearsal_gate: str | None = None, api: Any = None,
             check_lease: Callable[[], None] = lambda: None, swarm_root: Path | None = None,
             extending: bool = True) -> Nightly:
    """The job over the real boxes. `extending` (every caller but `schedule`): `preflight` must pass (the gate image holds
    a holdout for every root of the swarm and the chain is on it), or nothing is woken, pulled or copied (THE CHAIN'S
    RULE: a forward chain on another image would replace the swarm's gate). `run_real` calls `preflight` before it wakes
    the data box; this is the backstop for any other caller."""
    import boxlib as bl

    api = api or bl.client()
    images = bl.read_json(bl.IMAGES)
    gate = {"box_id": rehearsal_gate} if rehearsal_gate else ((images.get("gate") or {}).get("current") or {})
    if not gate.get("box_id"):
        raise RuntimeError("no gate image recorded in images.json; build it first (images.py build gate)")
    if extending and not rehearsal_gate:
        preflight(images, swarm_root)
    gym_ids = [e.get("box_id") for e in (images.get("gym") or {}).get("history", []) if e.get("box_id")]
    data = BoxHandle(api, bl.data_box_id(), defer_sleep=True)
    data.wake()
    calendar_json = json.loads(api.download(data.box_id, "/data/work/calendar.json"))
    calendar = sl.Calendar.from_json(calendar_json["exceptions"])
    try:
        status = str((api.get(gate["box_id"]) or {}).get("status", ""))
    except bl.SailboxError as error:
        if error.status != 404:
            raise
        status = "terminated"
    if status in ("terminated", "terminating", "failed", "create_failed"):
        if rehearsal_gate:
            raise RuntimeError("the rehearsal gate no longer exists")
        checkpoint_id = images["gate"].get("current_checkpoint") or gate["checkpoints"][0]
        check_lease()
        new = api.from_checkpoint(checkpoint_id, name="ltcm-gate-image-forward", timeout=1800)
        gate["box_id"] = new["sailbox_id"]
        from images import seal

        seal(api, gate["box_id"])
        check_lease()
        bl.write_json(bl.IMAGES, images)
    gate_handle = BoxHandle(api, gate["box_id"])
    gate_handle.wake()
    document = (api.egress(gate_handle.box_id) or {}).get("document", {})
    if document.get("no_network") is not True:
        raise RuntimeError("the forward target is not sealed")
    api.exec(gate_handle.box_id, ["test", "-f", "/data/store/GATE"], timeout=60).check()
    check_lease()
    bl.push_code(api, gate_handle.box_id)
    last_args = (bl.read_json(bl.DATA_BOX).get("runs") or [{}])[-1].get("args")

    def checkpoint() -> str:
        from images import checkpoint_with_retry

        row = checkpoint_with_retry(api, gate["box_id"], name=f"ltcm-gate-{bl.now().replace(':', '')}",
                                    ttl_seconds=(2 if rehearsal_gate else 365) * 86400, check_lease=check_lease)
        return row["checkpoint_id"]

    def relay(day, handle, source_incomplete=None):
        from sip import relay_day

        return relay_day(day, handle, check_lease=check_lease, source_incomplete=source_incomplete)

    return Nightly(data=data, gate=gate_handle, images=images, save=lambda d: bl.write_json(bl.IMAGES, d),
                   checkpoint=checkpoint, calendar=calendar, last_backfill_args=last_args, gym_box_ids=gym_ids,
                   rehearsal=bool(rehearsal_gate), relay=relay, sip_check=sip_proof, check_lease=check_lease)


def sip_proof(day: dt.date, handle: Any, source_incomplete: Sequence[str] = ()) -> dict[str, Any]:
    """The day's SIP proof from the data box's current files (`backfill.py sip-status`): every root complete, or (THE
    SOURCE GAP) short only where the forward gap ledger names it (`source_incomplete`), each such root said with the
    canonical file it keeps and that file's source label, under `status` "source_incomplete". Raises otherwise."""
    import boxlib as bl
    from sip import status_day

    rows = status_day(handle, day)['roots']
    short = [r for r in rows if not r.get('complete')]
    if any(r['root'] not in set(source_incomplete) for r in short):
        raise RuntimeError('forward SIP coverage is incomplete; no gate copy or checkpoint')
    proof = {'schema': sl.SIP_COVERAGE_SCHEMA, 'status': 'source_incomplete' if short else 'complete', 'day': str(day),
             'verified_at': bl.now(), 'scope': 'stock_underlying_completed_grid', 'roots': [r['root'] for r in rows],
             'files_sha256': hashlib.sha256(json.dumps([(r['root'], r['file_sha256']) for r in rows],
                                                      sort_keys=True).encode()).hexdigest()}
    if short:
        proof['source_incomplete'] = [{'root': r['root'], 'status': r.get('status'), 'file_sha256': r.get('file_sha256'),
                                       'canonical_source': str(r.get('source') or '')[:120]} for r in short]
    return proof


def run_real(day: dt.date | None = None, *, rehearsal_gate: str | None = None,
             dry_run: bool = False, swarm_root: Path | None = None) -> dict[str, Any]:
    import boxlib as bl

    if not rehearsal_gate:
        preflight(bl.read_json(bl.IMAGES), swarm_root)  # THE CHAIN'S RULE: a refused night wakes no box
    api = bl.client()
    data_box = bl.data_box_id()
    bl.ensure_running(api, data_box)
    job = None
    with bl.RemoteLease(api, data_box) as lease:
        try:
            # Gate recovery/verification and code changes are covered by the same cross-host lease.
            job = real_job(rehearsal_gate=rehearsal_gate, api=api, check_lease=lease.check, swarm_root=swarm_root)
            lease.check()
            bl.push_code(api, data_box)
            result = job.run(day, dry_run=dry_run)
            job.gate.sleep(None)
            if not job.data.backfill_running():
                job.data.sleep(next_wake(job.clock(), job.calendar).strftime("%Y-%m-%dT%H:%M:%SZ"))
        except BaseException:
            # Sleep only while we still own the gate. A lost lease may have a new controller.
            try:
                if job is not None:
                    lease.check()
                    job.gate.sleep(None)
            except Exception:
                pass
            raise
    job.data.flush_sleep()  # release the data-box lease before putting its holder to sleep
    return result


def publish_ready(path: Path, result: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    """Only a completed, checkpointed forward day becomes visible to the swarm; no data leaves. The document names the
    gate image the chain extends (`base_checkpoint`) and the roots that image holds a holdout for (`holdout_roots`): the
    swarm takes the checkpoint only when they are the gate `swarm.json` names and cover its roots (THE CHAIN'S RULE,
    league/swarm/settings.py `ready_refusal`). A day finished without them (by a release before they were recorded) is
    not published (`published` false): the day is complete on the gate, and the next day's publish names its chain.
    THE SOURCE GAP: `sip_coverage` is the day's proof (`status` "source_incomplete" with its short roots when the ledger
    holds one), and `source_incomplete` lists every root-day the ledger holds on this chain, each never complete."""
    import boxlib as bl

    if not result.get("checkpoint") or not str(result["checkpoint"]).startswith("sbcp_"):
        raise ValueError("a completed gate checkpoint is required")
    day = dt.date.fromisoformat(result["day"])
    if sl.window_of(day) != "forward":
        raise ValueError("only forward days can be published")
    base, held = result.get("base_checkpoint"), result.get("holdout_roots")
    document = {"schema": 1, "gate_checkpoint": result["checkpoint"], "base_checkpoint": base,
                "holdout_roots": list(held) if isinstance(held, (list, tuple)) else None, "day": day.isoformat(),
                "ready_at": now.isoformat(), "roots": list(result.get("roots") or ()),
                'sip_coverage': result.get('sip_coverage') or {'status': 'legacy_unverified'},
                'source_incomplete': list(result.get('source_incomplete') or ())}
    if not (isinstance(base, str) and base.startswith("sbcp_")) or not document["holdout_roots"]:
        return {**document, "published": False,
                "why": "the day's record does not name the gate image it extends and that image's roots"}
    previous = bl.read_json(path)
    if str(previous.get("day", "")) <= day.isoformat():
        bl.write_json(path, document)
    return document


def stamp_ready(ready_file: Path, *, apply: bool = False) -> dict[str, Any]:
    """THE CHAIN'S RULE, the deploy step (Oct 1, 2026): name the gate image in a LEGACY ready file (one written before
    the nightly wrote `base_checkpoint`), so the swarm never needs images.json to prove it. Only a file the swarm already
    takes under the legacy proof (`settings.ready_refusal`) is stamped, with that image's first checkpoint and recorded
    roots; after the write the swarm must take it with the same gate checkpoint, or the old file is put back. Holds the
    daemon's `nightly.lock` (the daemon holds it while it runs: stop it first), so no publish can race the write. A dry
    run (`apply` false) says what it would write."""
    import boxlib as bl
    from league.swarm import settings as swarm_settings
    from locking import process_lock

    root = ready_file.parent
    with process_lock(bl.STATE_DIR / "nightly.lock"):
        ready = bl.read_json(ready_file)
        if not ready:
            raise RuntimeError(f"no readable ready file at {ready_file}")
        if "base_checkpoint" in ready:
            return {"stamped": False, "why": "the ready file already names its gate image", "ready": ready}
        before = swarm_settings.load(root)
        if (before.get("forward") or {}).get("ready") != ready:
            why = ((before.get("forward") or {}).get("ready_ignored") or {}).get("why") or "the swarm does not take it"
            raise RuntimeError(f"refused: the swarm does not take this ready file ({why}); nothing was written")
        current = (bl.read_json(root / "data" / "images.json").get("gate") or {}).get("current") or {}
        stamped = {**ready, "base_checkpoint": current["checkpoints"][0],
                   "holdout_roots": sorted({str(r).upper() for r in current["roots"]})}
        if not apply:
            return {"stamped": False, "would_write": stamped}
        bl.write_json(ready_file, stamped)
        after = swarm_settings.load(root)
        if (after["gym"].get("gate_checkpoint") != before["gym"].get("gate_checkpoint")
                or "ready_ignored" in (after.get("forward") or {})):
            bl.write_json(ready_file, ready)
            raise RuntimeError("the stamped ready file did not stand with the same gate; the original was put back")
        return {"stamped": True, "ready": stamped, "gate_checkpoint": after["gym"].get("gate_checkpoint")}


def retrying(prior: Any, day: dt.date, error: BaseException, now: dt.datetime) -> dict[str, Any]:
    """`nightly.json` `retrying`: the day the controller retries, since when, how many tries, and (when the error is a SIP
    gap: `SIPError.coverage`) the short roots with their coverage and when the day goes on if their packets stay as they
    are (`handoff_at`, THE SOURCE GAP), for the stall alarm (`league/ops/stall.py` `forward`). A try that fails another
    way keeps what the last gap named."""
    prior = prior if isinstance(prior, Mapping) and prior.get("day") == day.isoformat() else {}
    out = {"day": day.isoformat(), "since": prior.get("since") or now.isoformat(),
           "attempts": int(prior.get("attempts") or 0) + 1, "last_error_at": now.isoformat()}
    gaps = getattr(error, "coverage", None)
    if isinstance(gaps, list) and gaps and all(isinstance(g, Mapping) for g in gaps):
        out["roots"] = sorted({str(g.get("root")) for g in gaps})
        out["gaps"] = [{"root": str(g.get("root")), "known": g.get("known"), "expected": g.get("expected"),
                        "missing_minutes": list(g.get("missing_minutes") or [])[:12], "packet_sha256": g.get("packet_sha256")}
                       for g in sorted(gaps, key=lambda g: str(g.get("root")))]
        out["handoff_at"] = getattr(error, "handoff_at", None)
    else:
        out.update({k: prior[k] for k in ("roots", "gaps", "handoff_at") if k in prior})
    return out


class Controller:
    """A durable schedule; a failed night stays pending, and outages are caught up oldest first."""

    def __init__(self, state: Path, ready_file: Path, calendar: sl.Calendar, *,
                 run: Callable[[dt.date], dict[str, Any]], retry_seconds: int = 300,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)):
        self.state, self.ready_file, self.calendar = state, ready_file, calendar
        self.run, self.retry_seconds, self.clock = run, retry_seconds, clock

    def tick(self) -> dict[str, Any]:
        import boxlib as bl

        now = self.clock()
        record = bl.read_json(self.state / "nightly.json")
        finished = record.get("completed", {})
        pending = due_days(now, self.calendar, finished)
        if not pending:
            return {"phase": "waiting", "next_wake": next_wake(now, self.calendar).isoformat()}
        if float(record.get("retry_at", 0)) > now.timestamp():
            return {"phase": "retry", "retry_at": record["retry_at"], "error": record.get("error")}
        day = pending[0]
        try:
            result = self.run(day)
            ready = publish_ready(self.ready_file, result, self.clock())
        except Exception as error:
            record.update({"error": f"{type(error).__name__}: {str(error)[:500]}",
                           "retry_at": self.clock().timestamp() + self.retry_seconds, "day": day.isoformat(),
                           "retrying": retrying(record.get("retrying"), day, error, self.clock())})
            bl.write_json(self.state / "nightly.json", record)
            return {"phase": "retry", **record}
        finished[day.isoformat()] = ready["gate_checkpoint"]
        record.pop("retrying", None)
        record.update({"completed": finished, "error": None, "retry_at": 0, "day": day.isoformat(),
                       "completed_at": self.clock().isoformat(),
                       "source_incomplete": [{"day": g.get("day"), "root": g.get("root")}
                                             for g in ready.get("source_incomplete") or [] if isinstance(g, Mapping)]})
        if ready.get("published") is False:
            record["unpublished"] = {"day": day.isoformat(), "why": ready.get("why")}
        bl.write_json(self.state / "nightly.json", record)
        return {"phase": "complete", "day": day.isoformat(), "gate_checkpoint": ready["gate_checkpoint"],
                "published": ready.get("published", True)}


def window_hook(state: Path) -> str | None:
    """One tick of the history fetch's controller when it is enabled and no standalone controller holds it."""
    try:
        from window import daemon_tick

        return daemon_tick(state)
    except (Exception, SystemExit) as error:  # noqa: BLE001 - the nightly comes first
        return f"error {type(error).__name__}: {str(error)[:200]}"


def daemon(state: Path, ready_file: Path, *, poll: float = 30.0) -> int:
    import boxlib as bl
    from locking import process_lock

    calendar_file = state / "calendar.json"
    calendar = sl.Calendar.from_json(json.loads(calendar_file.read_text())["exceptions"])
    stop = threading.Event()
    finished = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    status: dict[str, Any] = {"phase": "starting"}
    release = str(Path(__file__).resolve().parents[2])
    start = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]
    identity = {"pid": os.getpid(), "start": start, "release": release}

    def heartbeat():
        while not finished.is_set():
            bl.write_json(state / "nightly.heartbeat", {**identity, "at": time.time(), **status,
                                                       "state": status.get("phase"),
                                                       "busy": status.get("phase") == "running"})
            finished.wait(30)

    def run(day):
        status.clear()
        status.update({"phase": "running", "day": day.isoformat()})
        return run_real(day, swarm_root=ready_file.parent)  # the swarm's root holds its ready file and swarm.json

    with process_lock(state / "nightly.lock") as lock:
        lock.seek(0)
        lock.truncate()
        json.dump(identity, lock)
        lock.flush()
        os.fsync(lock.fileno())
        (state / "nightly.pid").write_text(str(os.getpid()))
        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        controller = Controller(state, ready_file, calendar, run=run)
        try:
            while not stop.is_set() and not (state / "nightly.stop").exists():
                result = controller.tick()
                status.clear()
                status.update(result)
                # The long history fetch (window.py): paused for the quiet window, resumed only after the night's
                # checkpoint. Same thread as the nightly, so the two never overlap; it never raises into this loop.
                window = window_hook(state)
                if window:
                    status["history_fetch"] = window
                if (not stop.is_set() and not (state / "nightly.stop").exists()
                        and bl.read_json(state / "completion-config.json").get("enabled") is True):
                    from complete import Completion

                    status.clear()
                    status.update({"phase": "running", "job": "store-completion"})
                    completion = Completion(state).tick()
                    status.clear()
                    status.update({**result, "completion": completion.get("phase"),
                                   "completion_error": completion.get("error")})
                stop.wait(poll)
        finally:
            stop.set()
            finished.set()
            worker.join(timeout=35)
            (state / "nightly.pid").unlink(missing_ok=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", default=None, help="controller records (default .data/gym)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--day", default=None)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--swarm-root", default=None, help="the swarm's state root, for gym.roots (default: --state's parent)")
    rh = sub.add_parser("rehearse", help="copy a holdout day the data box holds to a rehearsal gate box")
    rh.add_argument("--gate-box", required=True)
    rh.add_argument("--day", required=True)
    sub.add_parser("schedule")
    sub.add_parser("status")
    st = sub.add_parser("stamp-ready", help="name the gate image in a legacy ready file (stop the daemon first)")
    st.add_argument("--ready-file", required=True)
    st.add_argument("--apply", action="store_true", help="write it (default: say what would be written)")
    d = sub.add_parser("daemon", help="run the autonomous forward controller on the House")
    d.add_argument("--state", default=None, dest="daemon_state")
    d.add_argument("--ready-file", required=True)
    args = parser.parse_args(argv)
    state = getattr(args, "daemon_state", None) or args.state
    if state:
        os.environ["LTCM_GYM_STATE"] = state
        import boxlib as bl

        bl.configure_state(Path(state))
    if args.cmd == "daemon":
        import boxlib as bl

        return daemon(bl.STATE_DIR, Path(args.ready_file))
    if args.cmd == "status":
        import boxlib as bl

        nights = (bl.read_json(bl.IMAGES).get("gate") or {}).get("forward_days", {})
        print(json.dumps({"forward_days": nights,
                          "source_incomplete": {d: sorted(n.get("sip_gaps") or {}) for d, n in sorted(nights.items())
                                                if n.get("sip_gaps")},
                          "sip_watch": {d: {r: {k: w.get(k) for k in ("known", "expected", "first_seen", "attempts")}
                                            for r, w in (n.get("sip_watch") or {}).items()}
                                        for d, n in sorted(nights.items()) if n.get("sip_watch")},
                          "controller": bl.read_json(bl.STATE_DIR / "nightly.json"),
                          "heartbeat": bl.read_json(bl.STATE_DIR / "nightly.heartbeat")}, indent=1))
        return 0
    if args.cmd == "stamp-ready":
        print(json.dumps(stamp_ready(Path(args.ready_file), apply=args.apply), indent=1, default=str))
        return 0
    if args.cmd == "rehearse":
        print(json.dumps(run_real(dt.date.fromisoformat(args.day), rehearsal_gate=args.gate_box), indent=1, default=str))
        return 0
    if args.cmd == "schedule":
        job = real_job(extending=False)
        if job.data.backfill_running():
            print("the backfill is running; the data box stays awake")
            return 0
        wake = next_wake(dt.datetime.now(dt.timezone.utc), job.calendar).strftime("%Y-%m-%dT%H:%M:%SZ")
        job.data.sleep(wake)
        job.data.flush_sleep()
        print(f"the data box sleeps until {wake}")
        return 0
    day = dt.date.fromisoformat(args.day) if args.day else None
    swarm_root = Path(args.swarm_root) if args.swarm_root else None
    print(json.dumps(run_real(day, dry_run=args.dry_run, swarm_root=swarm_root), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
