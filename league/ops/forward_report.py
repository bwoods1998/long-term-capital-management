"""The `forward_report` job: the forward record's daily meters, its report file, its funnel counts and its alarms.

Owner: C (league/ops/E3_INTERFACES.md). Protected (release E3). After the forward shadow and 35 minutes before each
open; in a pause too. It writes `fwd_cey`, `fwd_meter` and `fwd_groups` of `<state>/forward.sqlite`
(league/ops/forward_db.py; first write stands a day) and `<state>/forward-report.json` (0600, atomic:
`context.write_json`). Operator only: nothing here reaches a generator, the scoreboard or the website.

THE METERS (`meters`; arithmetic in league/ops/forward_stats.py), for every forward day up to the last `fwd_runs`
`through` with no `fwd_cey` row, in order:
- N_eff AND CEY (D6). Day d; W = the last `NEFF_WINDOW` forward days up to d. A lineage's representative is its lowest
  pid whose reason is train_pass, seed or live, else its lowest pid; controls are excluded; above `neff_max_members`,
  those with the smallest `sha256("neff-1|" + key)` are kept (`representatives`). A member is a representative whose
  counted days inside W form an unbroken run of at least `NEFF_MIN_DAYS` sessions ending at d, with non-zero variance
  of x (`population`). cey_day(d) = N_eff(d) / 252; CEY(D) = the sum of cey_day over forward days d <= D;
  "provisional" while n_w < `NEFF_PROVISIONAL`; `median20` = the median cey_day of the last 20 forward days.
- THE REPLAY MULTIPLE (D7). `sim_py(D)` = (the sum, over swarm `runs` rows of equity-lane families (structure "etf" or
  "stock") with status not in `funnel.NOT_RUN` and trials > 0, of `json_extract(summary, '$.days') * trials`, plus the
  count of `fwd_days` rows of non-control pids, any engine, with day <= D) / 252 (`sim_program_years`). `hist_iy` = the
  history's independent years over 2016 through `config.LOOK_CAP`'s year, on the as-of close-to-close returns of the
  registered non-control NEEDS symbols (`elane.cfg(settings)["universe"]` when none) that have a bar on each session
  (`hist_independent_years`; prices only, read with the capability `GATE_REASON`; a `MissingData` leaves it and the
  multiple None that day). replay_multiple(D) = sim_py(D) / (hist_iy + CEY(D)). House only.
- THE BH/BY "ANY EDGE ANYWHERE" METER (D8). One p a lineage: the `p_x` of its representative's latest checkpoint (the
  largest n, a final one included) under the NEWEST engine that pid has a checkpoint for; a lineage with no
  checkpoint is outside it. The same over every control with a checkpoint, on its `p_x0` (the cost-free excess),
  gives `controls_bh`, `controls_by` and `controls_p10`. Reading: "none yet" while BY = 0; "unreliable" beside it
  while `controls_by` > 0.
- RC RECORDING AND READS (D9). Each forward day, for grp in {train_pass, train_fail (registry reasons), look_pass,
  look_fail (tags), seed, control:<g>}: n, `mean_x`, `mean_r`, `mean_w`, `mean_x0` (control groups) and `ugroups`. A
  pid is in a tag group on day d iff the tag's `at` is before `schedule.moments(d).close_at`. THE PAIRS: (look_pass,
  look_fail), (train_pass, train_fail), and each of those four against THE POOLED CONTROLS of that day (the unweighted
  mean of `mean_x0` of control:<g> over the base groups its `ugroups` name). A session is USABLE for a pair when both
  sides have n >= `RC_MIN_GROUP`; a pair's k-th read is taken the night of its `RC_READS[k]`-th usable session, over
  exactly those sessions (`rc_pairs`). NO DIFFERENCE IS COMPUTED OR SHOWN BEFORE A PAIR'S READ.

THE REPORT (`section`, written to `FILE`; read by the dlane report through `read_section`): `SECTION_KEYS`. Forward
rows reach only this file, the dlane report's `forward_record` section and `forward_twins.a14_reading`: no
per-program forward figure for a pid without a "live" tag, no RC difference before a pair's read, no figure of the
sealed memory tables (counts only). There is no running A14: A14 is read only at a Done checkpoint, by the Done
meter, over its own counted closes.

THE FUNNEL (`funnel_rows`, read by league/ops/funnel.py `window` as `forward_record`): INTEGERS ONLY (`FUNNEL_KEYS`).

THE ALARMS (`alarms`; `ALARMS`: id -> level). Each row is {"id", "level": "info" | "warning", "text", "new"}; the
dlane report carries them and each warning is also a `ctx.alert` of the job that finds it. EVERY TEXT HOLDS IDS, COUNTS
AND DATES ONLY: no decimal figure, no "bp", no "%", no return, no dollar figure. With `elane.forward.mode` off none
of FW1-FW8 is raised.
- FW1 (warning): the mode is "record" AND (no `fwd_days` row by 09:00 ET the next session for the last closed forward
  day on which at least one active registry row had `first_day` <= that day, OR the report is over `STALE_HOURS`
  old): a stalled job. Silent on an empty registry, on the sessions before a first registration's `first_day`, and
  while the mode is off.
- FW2 (warning): programs left stale two nights running, or a pid with a `data_failed` or a `run_failed` event on two
  nights running (counts in the text).
- FW3 (warning): a `restated` event written last night (written once a value, so this is its first night).
- FW4 (warning): `verify_chain` not ok (owner step: stop the forward jobs and compare with the backup).
- FW5 (warning): cey_day under its 20-day median for 10 forward days running while equity births continue.
- FW6 (warning): a live instance with 5 or more priced closes whose mean twin gap is beyond the A14 bound either
  way, or with 20 or more sessions under the A14 agreement bound (before any checkpoint); the text names the instance
  and the counts, no figure.
- FW7 (warning): while `eq_instances` holds a live row: the live book's kv `eq_decide` for the last session is status
  "failed", or status "done" with no `why` and `at` later than that session's `close_at` + 2,400 s.
- FW8 (warning): the equity fingerprint moved while a lineage is live (`identity_moved`).
- RR1 (warning): a declared release receipt unread 24 h after its window closed; RR2 (info): a receipt read "flat"
  or "wrong_way" (listed, never reverted).
- CP1 (info): a route unprobed for 45 days, or a readable 2025 or 2026H1 cell newly "recalled"; CP2 (warning): a route
  whose last three attempts added no cell.
- MM1 (warning): a `swarm.status` "elane_memory" alert in the last 24 h.

Standard library and numpy only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

FILE = "forward-report.json"
#: The reason the job mints its `EquityGateCapability` with (D7's hist_iy reads prices up to the look cap).
GATE_REASON = "forward-report"
#: The report file is stale past this many hours (`read_section` then gives None and `alarms` one FW1 row).
STALE_HOURS = 36.0
#: The report's top-level keys (`section`).
SECTION_KEYS = ("at", "mode", "t0", "through", "engine", "registry", "shadow", "checkpoints", "meter", "cey", "fills",
                "rc", "memory", "contamination", "receipts", "alarms")
#: `funnel_rows`' keys, every value an integer (never a figure).
FUNNEL_KEYS = ("registered", "registered_total", "lineages", "controls", "program_sessions", "program_sessions_total",
               "stale", "errors", "checkpoints", "bh", "by", "oof_seen", "oof_rows")
#: The alarms: id -> level (the module docstring).
ALARMS: dict[str, str] = {"FW1": "warning", "FW2": "warning", "FW3": "warning", "FW4": "warning", "FW5": "warning",
                          "FW6": "warning", "FW7": "warning", "FW8": "warning", "RR1": "warning", "RR2": "info",
                          "CP1": "info", "CP2": "warning", "MM1": "warning"}
#: The RC pairs among the program groups (D9); each of the four groups is also read against the pooled controls.
RC_PAIRS = (("look_pass", "look_fail"), ("train_pass", "train_fail"))


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py). With the mode "off" it writes {"at", "mode": "off", "alarms": []} to `FILE`
    and returns skipped; else `meters`, then `section` written to `FILE`; each warning alarm is also a
    `ctx.alert("warning", text)`. The receipt holds counts, never a figure."""
    raise NotImplementedError("C: league/ops/forward_report.py run")


def meters(root: str | Path, db: sqlite3.Connection, *, now: float, settings: Mapping[str, Any] | None
           ) -> dict[str, Any]:
    """The D6, D7, D8 and D9 rows of every forward day up to the last `fwd_runs` `through` that has no `fwd_cey` row,
    in order (first write stands: a second call writes nothing): {"days", "cey", "meter", "groups" (rows written)}."""
    raise NotImplementedError("C: league/ops/forward_report.py meters")


def representatives(db: sqlite3.Connection, day: str) -> list[int]:
    """D6's representatives on `day`: one pid a lineage (its lowest pid whose reason is train_pass, seed or live,
    else its lowest pid), controls excluded, cut to `neff_max_members` by the smallest `sha256("neff-1|" + key)`."""
    raise NotImplementedError("C: league/ops/forward_report.py representatives")


def population(db: sqlite3.Connection, day: str) -> tuple[list[str], Any]:
    """(the representatives' registry keys, X) for D6 on `day`: X an (N, T) float ndarray of daily excess over the
    window's forward days, NaN outside a member's unbroken run of counted days ending at `day`
    (`forward_stats.pairwise_corr`'s shape)."""
    raise NotImplementedError("C: league/ops/forward_report.py population")


def sim_program_years(root: str | Path, db: sqlite3.Connection, day: str) -> float:
    """D7's sim_py through `day` (the swarm store read-only)."""
    raise NotImplementedError("C: league/ops/forward_report.py sim_program_years")


def hist_independent_years(root: str | Path, symbols: Sequence[str]) -> float | None:
    """D7's hist_iy over `symbols` (`forward_stats.independent_years` on the store's as-of close-to-close returns, a
    year at a time through `config.LOOK_CAP`); None when the store cannot give it (`MissingData`)."""
    raise NotImplementedError("C: league/ops/forward_report.py hist_independent_years")


def rc_pairs(db: sqlite3.Connection, day: str) -> list[dict[str, Any]]:
    """D9 through `day`: one object a pair: {"a", "b", "usable" (its usable sessions so far), "next_read" (the count
    its next read is taken at; None after the last), "reads": [{"n", "day", "mean_bp", "t"}] (only the reads taken)}.
    No difference before a pair's read."""
    raise NotImplementedError("C: league/ops/forward_report.py rc_pairs")


def section(root: str | Path, *, now: float, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The report (`SECTION_KEYS`): `at`, `mode`, `t0`, `through`, `engine`, `registry` (counts by reason; stopped by
    cause; suspects), `shadow` (programs, sessions, stale, `run_failed`, `data_failed`, `run_disqualified`, the last
    `night_failed`), `checkpoints`, `meter` (with `engines`: the distinct engine ids in `fwd_days`), `cey` (with
    `neff_raw` beside), `fills` (timing, livelike, lots, participation, intents: agreed, disagreed by cause,
    unreadable), `rc` (one object a pair; group counts), `memory` (counts), `contamination`, `receipts`, `alarms`.
    Each object carries its tables' column names; what may appear is bounded by the module docstring."""
    raise NotImplementedError("C: league/ops/forward_report.py section")


def read_section(root: str | Path) -> dict[str, Any] | None:
    """`<root>/forward-report.json` as written; None when absent, unreadable or older than `STALE_HOURS`."""
    raise NotImplementedError("C: league/ops/forward_report.py read_section")


def funnel_rows(root: str | Path, start: float, end: float) -> dict[str, int]:
    """The forward record's counts in [start, end), INTEGERS ONLY (`FUNNEL_KEYS`): `registered` and `registered_total`,
    `lineages`, `controls`, `program_sessions` and `program_sessions_total` (non-control `fwd_days` rows), `stale`,
    `errors`, `checkpoints`, `bh`, `by`, and from the swarm store read-only `oof_seen` and `oof_rows` (the seen-fact
    and out-of-fold rows with `at` in the window: `elane_memory.counts`' tables). An absent forward store or memory
    table is zeros (nothing was recorded); an unreadable one raises."""
    raise NotImplementedError("C: league/ops/forward_report.py funnel_rows")


def alarms(root: str | Path, *, now: float, settings: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """The forward alarms for the dlane report: [] when `forward_db.mode(settings)` is "off" or the file says `mode`
    "off"; the file's alarms when it is under `STALE_HOURS` old; else one FW1 row. Every row is {"id", "level",
    "text", "new"}. Never raises for a missing or unreadable file."""
    raise NotImplementedError("C: league/ops/forward_report.py alarms")


__all__ = ["FILE", "GATE_REASON", "STALE_HOURS", "SECTION_KEYS", "FUNNEL_KEYS", "ALARMS", "RC_PAIRS", "run", "meters",
           "representatives", "population", "sim_program_years", "hist_independent_years", "rc_pairs", "section",
           "read_section", "funnel_rows", "alarms"]
