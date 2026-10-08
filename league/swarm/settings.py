"""The swarm's settings: defaults, overlaid by `league/config.json` ("gym" and "swarm"), then by the repo's
`league/swarm/policy.json`, then by `<root>/swarm.json` (the operator's file on the box: a change there needs no deploy;
the process re-reads it every loop).

SETTINGS AS CODE (V3-A, Oct 2, 2026). `policy.json` is the research settings as reviewed code: a pull request changes
it, so the swarm is tuned in the repository, not by a laptop command editing the box's file. Since the WP8 review the
file is protected (`league/ci.py` FORBIDDEN, the gateway's list with it): the gateway merges no change to it and the
updater ships none, so a merged change reaches the box by the owner's deploy alone, and until that deploy the updater
refuses every later release too (it compares each one with the running release). It has the shape of `swarm.json`
and sits between config.json and swarm.json: DEFAULTS < config.json < policy.json < swarm.json. The owner's switches
(`OWNER_KEYS`: `enabled`, `live`) are never read from it (a key there is ignored and named in `_policy`); they stay in
swarm.json, which after the V3-A migration (`scripts/settings_migrate.py`) holds only them. A missing policy.json is no
layer (exactly as before); one that is not a JSON object, or whose shape breaks the defaults' (`policy_shape`), is
ignored whole, and the loop alerts once (`_policy`).

The EVIDENCE LINES are not settings: they are the plan's, in `evidence.py`, and loosening one is the
owner's decision. Everything here is throughput and money: how many, how often, how much.

THE 2020-21 SWITCH (`gym.train_from`, Sept 27, 2026). Train's first day: "2022-01-03" (the default: Train is 2022-2024,
exactly as before) or "2020-01-02" (Train is 2020-2024: the COVID crash and rebound and 2021's low-volatility bull join
the worst-year score); nothing else. The setting is what the swarm's NEXT START migrates to
(`researcher.migrate_objective`, which re-chooses every family's best from runs over that span only); until then the
running swarm keeps scoring, stamping and running Train over the span its store was migrated to (`objective_span` of
`store.get("train_objective")`), and the loop raises one `swarm.status` alert that a restart is pending. Switching it on
also needs a Gym image that holds those years (`images.py build gym --train-from 2020-01-02`, adopted as
`gym.image_checkpoint` in the same edit): the pool refuses a Train run on an image whose first Train day is not the
span's (both ways). A date in the first days of January snaps to that year's first session (2020-01-01 is 2020-01-02);
any other value, and a missing one while Train is not 2022-2024, keeps the running span (a typo never switches Train back
to 2022), and the loop keeps raising an alert naming it until it is fixed. With the switch on, `train_split` and
`run_timeout_seconds` follow the span unless the operator sets them (`train_split`, `run_timeout`: 16 and 1500 s over
five years, 8 and 900 s over three).

TRAIN FROM 2017 (Sept 29, 2026). A third start, "2017-01-03" (Train is 2017-2024: 2017's calm, the February 2018
volatility shock and the fourth-quarter 2018 selloff, 2019, then 2020-2024), with its own Gym image
(`images.py build gym --train-from 2017-01-03`); everything above holds unchanged for it (the snap: 2017-01-01 and
2017-01-02 are 2017-01-03; the derived split 24 and time limit 2400 s over eight years). Nothing moves until the
operator writes it with the matching image; "2020-01-02" and "2022-01-03" mean what they meant.

THE BUDGET (LTCM v3, the owner's D4; its rule version 2, Oct 3, 2026). The research dollars a day are not settings
either: `league/ops/budget.py` computes them from the owner's ceiling and the meters' runways into `<state>/budget.json`,
and `load` applies them LAST and only to tighten: min() against `researcher.sail_usd_per_hour` (or
`researcher.usd_per_hour` while that is unset), `gym.max_boxes`, `claude.role_usd_day` (a line for every role in
`claude.roles`) and `population.ceiling` (the budget's ceiling is never under `population.floor` plus its birth margin),
with `population.start` held to the tightened ceiling; max() against `architect.every_seconds` and
`architect.refill_seconds` (each its own knob; while the tightened ceiling holds the start down, the refill is held
to the scheduled cadence); and `guard.openai_cap_usd` is tightened to 0 (OpenAI is no meter of the rule). So the layers
under it (this file's DEFAULTS, policy.json, swarm.json) are caps the budget works inside: a knob the budget would give
is reached only where they allow it (policy.json's `gym.max_boxes`, `researcher.sail_usd_per_hour`, the cadences and
the role lines are set with the owner's ceiling in mind). The `budget` block it sets (never the operator's: a `budget`
key in swarm.json is replaced) caps the Sail guard's day, with the last part of it kept for validation, the gate and
the nightly forward, and the paid models' room (Claude's, and OpenAI's under the same line, with the gate's review and
audit holds kept in it). A missing, unreadable or malformed budget.json is the floor; a stale one never loosens (each
meter the lower of the floor and what the stale file said).
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[2]

#: Train's first day by default and at its earliest, and its last day (league/gym/day.py's windows; a test holds them
#: equal). The swarm is standard library only, so they are repeated here rather than imported from the Gym.
TRAIN_CORE_START = dt.date(2022, 1, 3)
TRAIN_EARLIEST = dt.date(2017, 1, 3)
TRAIN_END = dt.date(2024, 12, 31)
#: The first session of each year Train may start in: the only values `gym.train_from` takes (2017 since Sept 29, 2020
#: since Sept 27, 2022 as ever).
TRAIN_STARTS = {2017: TRAIN_EARLIEST, 2020: dt.date(2020, 1, 2), 2022: TRAIN_CORE_START}
#: The Train split and run timeout over three years (the defaults before the switch); `train_split` and `run_timeout`
#: scale them with the span unless the operator sets `gym.train_split` or `gym.run_timeout_seconds`.
BASE_TRAIN_SPLIT = 8
BASE_RUN_TIMEOUT = 900

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    # The population (plan: 48 at the start of the training burst, a ceiling of 96, a floor of 16).
    # `reseed_max`: families a main-loop pass founds from the seeds on untried roots while below the start and the architect
    # is not due (`Swarm.reseed`). Off (0) by default: reseeds fill the gap the architect's refill cadence keys on, so a
    # swarm that reseeds sees the architect every `every_seconds` instead of every `refill_seconds`.
    # `floor_researching` (F1, Oct 3, 2026; researcher.py THE TURNOVER): the floor counts the living families that are
    # researching, so a dead slot (the idle rule finds it dead, or its researcher held `researcher.retire_hold_cycles`
    # cycles in a row with nothing pending) may retire at the floor; false counts every living family, as before.
    "population": {"start": 48, "ceiling": 96, "floor": 16, "reseed_max": 0, "floor_researching": True},
    "researcher": {
        # DeepSeek-V4-Flash at asap for the inner loop. V4.1-Flash (`long_profile`) is for long, well-cached histories:
        # measured Sept 26 at the cache share a trimmed history gets (44-66%), it cost four times V4-Flash a call, so it
        # is off unless `long_history_chars` is lowered.
        "profile": "flash_asap",
        "long_profile": "flash41_asap",
        "long_history_chars": 10 ** 9,
        # One rewrite after a stall of `stall_revisions`: V4-Pro asap, Kimi-K3 balanced for the top ten; asked in the
        # background, capped and spaced, never over the swarm's hourly pace.
        "rewrite_profile": "pro_asap",  # balanced took minutes on Sept 26 (the main session chose asap)
        "rewrite_usd_day": 1.0,         # a family's rewrites a day, on their own fuse
        "top_rewrite_profile": "k3_balanced",
        "top_rewrite_families": 10,
        # The top `top_families` by allocation share (`families.weight`) run every cycle on a stronger profile at low
        # effort (the sprint, Sept 26); the rest stay on `profile`. Null `top_profile` turns it off. The hourly pace
        # below governs these cycles too.
        "top_profile": "pro_asap",
        "top_reasoning_effort": "low",
        "top_families": 10,
        "top_max_output_tokens": 12000,  # low effort's reasoning (1,800-3,800 tokens measured) and a whole program
        # THE TOP BAND ON CLAUDE (Sept 29, 2026, the owner's decision: be bold with Claude Sonnet 5.5; researcher.py and
        # claude_research.py). The top `claude_top` by allocation share run their cycles on Claude while "researcher" is
        # in `claude.roles`; 0 turns it off. Every Claude failure finishes the turn on the family's Sail profile above.
        "claude_top": 12,                # on `claude.role_model.researcher` (Claude Sonnet 5.5)
        "claude_effort": "medium",       # low | medium | high | xhigh | max (Anthropic: medium for multistep tool use)
        "claude_max_tokens": 12000,      # thinking and the answer together, streamed; sizes the hold (~$0.33 on a mean body)
        "claude_timeout_seconds": 180,   # one call's overall limit (120 s is allowed between events)
        "claude_family_usd_day": 15.0,   # one family's Claude spend a UTC day (holds included): a fuse
        "claude_min_room_usd": 25.0,     # funded Claude room the researcher never takes: the architect, audit and diagnostician's
        "claude_hold_every": 3,          # in a hold streak with nothing new, Claude answers every 3rd cycle, Sail the rest (1: all)
        "claude_breaker_failures": 3,    # unknown-bill failures (a cut stream, a 5xx, a 429) in the window that pause the band
        "claude_breaker_window_seconds": 3600,
        "claude_breaker_pause_seconds": 3600,  # the band's cycles run on Sail while paused (kv `claude_band`); one overrun pauses it
        "stall_revisions": 5,
        "rewrites_per_day": 4,
        "rewrite_min_hours": 1.0,
        # Measured Sept 26 on a cycle's revise turn: effort low spent 1,800-3,800 reasoning tokens (100-180 s under load);
        # minimal and none spent none (28-64 s for the same turn, the whole program rewritten). Minimal keeps a cycle
        # under three minutes; the stall's rewrite thinks harder on a stronger model.
        "reasoning_effort": "minimal",
        "max_output_tokens": 8000,
        "max_model_calls": 3,          # a cycle's model calls (revise, read, ...)
        "min_call_seconds": 75,         # a later model call starts only with this much of the cycle left
        "max_tool_calls": 8,            # a cycle's tool calls
        # `gym_sweep` (R3, Sept 27): many PARAMS variants of one program in one call, in place of the cycle's one gym_run.
        # Every variant is a trial; the whole sweep counts as one revision. The pool had no spare boxes when it shipped
        # (Sept 27: every one of its boxes awake, ~1,300 jobs an hour at ~20 box-seconds a job), so both limits start
        # small: a sweep's variants, and the variants of every sweep in flight together (a sweep beyond that is refused
        # and the researcher runs gym_run that cycle). Raise them in swarm.json while gym_seconds' p90 and the pool's
        # abandoned jobs stay low.
        "sweep_enabled": True,
        "max_sweep_variants": 6,
        "max_sweep_jobs_in_flight": 24,
        "cycle_seconds": 170,           # a cycle's wall-time budget (target under 3 minutes)
        "history_cycles": 4,            # cycles of conversation kept (older ones live in the notebook) ...
        "history_trim_to": 2,           # ... cut back to this many at once, so the cached prefix holds for a few cycles
        "old_output_chars": 2500,       # tool outputs older than the last cycle, shortened to this
        "concurrency": 48,              # researchers in flight at once
        # The swarm's model spend an hour (Sail models + OpenAI over the last hour): a researcher starts no cycle above it.
        # Measured Sept 26: 22 researchers at ~44 s cycles spent ~$5/h before the cache fixes; the plan's figure is $1-2/h.
        "usd_per_hour": 4.0,
        # Optional independently funded Sail pace. When set, this replaces the combined hourly check above;
        # OpenAI remains governed by its funded gateway month and the swarm's own OpenAI burst cap/holds.
        "sail_usd_per_hour": None,
        "family_usd_day": 3.0,          # each family's daily model budget (the Provider's desk cap): a fuse
        "floor_usd_day": 150.0,         # every model call of the swarm together, a day (the Provider's floor cap): a fuse
        "idle_seconds": 5,              # between a family's cycles
        # Holds survive restarts and resume only on new evidence, guidance, data or a harness release. False restores
        # the legacy timer below. A researcher may retire an exhausted mechanism before choosing to wait.
        "hold_until_news": True,
        # PARKED DORMANCY (F1, Oct 3; loop.py `Scheduler.count_parked`): a park until news counts one dormant cycle each
        # `hold_idle_seconds` it lasts (no model call), up to `dormant_cycles`, so the dormancy clause retires a family
        # that only waits. False: a parked family's dormant count never moves (the standstill of Oct 3).
        "parked_dormancy": True,
        "retire_min_trials": 10,         # evidence-backed abandonment before a first hold, down to population.floor
        # HOLD BACKOFF (R4, Sept 28: 2,223 of 2,364 cycles in ten minutes were holds, a holding family back every ~12 s,
        # ~$6.6/h of holds against a $4.5/h pace). A family whose cycle ended in a hold with no new evaluation (and no run
        # queued) waits `hold_idle_seconds` before its next turn; news lifts the wait at once (a result of its own landed,
        # a gate verdict or validation, its gate place or band changed, a rewrite is ready: `loop.Scheduler`). The wait
        # doubles for each dormant cycle past `dormant_cycles` (a family the idle rule exempts: awaiting validation, at the
        # gate, at the floor), up to `hold_idle_max_seconds`; below that count it never doubles, so the dormancy clause
        # still decides a family that only holds within about `dormant_cycles` x `hold_idle_seconds`. 0 or null `hold_idle_seconds` turns the backoff off (`idle_seconds` alone);
        # null `hold_idle_max_seconds` turns the doubling off (`loop.hold_wait`).
        "hold_idle_seconds": 300,
        "hold_idle_max_seconds": 1800,
        "note_every_cycles": 6,         # a public note to the tape at most this often per family
        # The idle rule (R3, Sept 27): a Gym family with this many Gym evaluations since its birth or last validation and
        # no eligible Train version (or three times as many with a best Train score below zero) is dead, unless a
        # validated version awaits the gate. It may retire at `population.start` (only `population.floor` holds it),
        # and the tournament retires it if it does not. 0 or null turns the rule off (`researcher.idle_dead`).
        "retire_idle_evaluations": 150,
        # No duplicate runs (R3, the harness audit of Sept 28: 45% of trials were identical re-runs): a run or sweep variant
        # the family already evaluated (program, merged params, stress, window, roots, Gym image and engine) is answered
        # from the store, no job and no trial; false runs it again. A REVISE turn may hold (gym_run hold=true) instead.
        "reuse_results": True,
        # The idle rule's dormancy clause: a family whose last this-many cycles made no new Gym evaluation (only stored
        # results and holds) is dead, unless its best awaits validation; 0 or null turns the clause off.
        "dormant_cycles": 40,
        # THE HOLD OFFER (R11-1, Sept 29): a family that held this many cycles in a row with an eligible Train run behind it,
        # or `retire_hold_trials` trials, is offered `retire` on its REVISE turn too (down to `population.floor`); its
        # lesson is SELF-REFUTED. 0 cycles turns it off; 0 trials leaves the eligible run alone.
        "retire_hold_cycles": 3,
        "retire_hold_trials": 10,
        # F1 (Oct 3): the hold offer whatever the trial count (six of the eight families alive that day had 3 to 9 trials,
        # no eligible Train run and notes that asked to retire). False: an eligible run or `retire_hold_trials`, as above.
        "retire_hold_untested": True,
        # THE DEPTH RULE (F1, Oct 3; `researcher.short_dead`, a clause of the idle rule): a family whose latest counted
        # validation met at most `retire_short_checks` of the line's checks retires `retire_short_cycles` cycles after
        # it; one that met more keeps researching. 0 or null in either turns the rule off.
        "retire_short_checks": 5,
        "retire_short_cycles": 10,
        # THE EXTENSION HOLD (R11-4's swarm rule): a family whose latest validation met this many of the line's checks is
        # exempt from the dormancy clause until the operator clears its flag (its 2017-19 extension result landed:
        # scripts/extension_hold.py). 0 or null turns the rule off.
        "extension_hold_checks": 6,
        # THE ZERO-TRADE PROBE (R11-6): a Train year (2022, where most triggers fire) switches it on: a new version's first
        # Train run is preceded by a run over that year on the family's first root, and a probe with no trade is the
        # answer (disqualified, one trial) instead of the five-year run; `gym_run` full=true skips it. Null: off (the
        # operator switches it on in swarm.json). `probe_timeout_seconds`: a probe not back by then says nothing.
        "probe_year": None,
        "probe_timeout_seconds": 300,
    },
    "gym": {
        "enabled": False,
        "image_checkpoint": None,        # the Gym image (W1: .data/gym/images.json); forks are sealed
        "gate_checkpoint": None,         # the gate image (holdout and forward days); gate boxes only
        "start_boxes": 4,
        "max_boxes": 8,
        "batch_programs": 8,            # programs a batch runs day-major on one box
        "batch_wait_seconds": 8,        # how long a short batch waits for company
        "workers": 8,
        "split": 8,                      # the inner loop's segments (latency: one program, 3 years, 8 cores)
        # None: follow Train's span (`train_split`: 8 over three years, 16 over five, two full waves of 8 workers). A
        # number is the operator's and wins.
        "train_split": None,
        "validation_split": 1,          # Validation, holdout and forward run whole (the Gym refuses to split them)
        "run_timeout_seconds": None,     # None: follow Train's span (`run_timeout`: 900 s over three years, 1500 over five)
        "idle_sleep_seconds": 600,      # a box idle this long sleeps (sleeping boxes cost nothing)
        "box_usd_hour": 0.20,           # a busy l box (Sail bills measured use; $0.12-0.20/h measured Sept 26)
        "remote_root": "/workspace/gym",
        "store_root": "/data/store",
        "python": "/opt/data-venv/bin/python",  # the Gym image is a fork of the data box: its venv has numpy and pyarrow
        "capital": 10000.0,
        "roots": ["SPY", "QQQ", "IWM", "XSP", "SPXW"],
        # Train's first day (the module docstring's switch): "2020-01-02" or "2017-01-03" with a Gym image that holds
        # those years; "2022-01-03" to switch back. Unset: the running span stays (2022-01-03 on a store never
        # switched).
        "train_from": None,
    },
    # A robustness run waiting this long (its 1.5x run; the mid run twice as long) takes a Train job's priority (aging).
    "pool": {"robust_age_seconds": 600},
    "tournament": {
        "every_seconds": 3600,
        # THE IDLE PASS (R4, Sept 28): the idle rule's retirements alone (`researcher.idle_dead`: the hourly round's own
        # fallback, the same floor and exemptions) every this many seconds between the hourly rounds, so a dead family
        # leaves within minutes (the operator retired 60 by hand after R3). 0 or null: the hourly round only.
        "retire_every_seconds": 300,
        "explore_share": 0.25,
        # Read only by the Thompson bandit (`allocation.mode` "bandit"; the default allocator's knobs are swarm.json's
        # `allocation` block, league/swarm/allocation.py). THE EXPLOIT POOL (R11-5): only old families with a positive
        # latest validation mean are exploited, each earning at most this share; the explore pool (new families and old
        # ones at zero or below) takes the rest, never less than `explore_share`. Null: `explore_share` alone.
        "exploit_per_positive": 0.15,
        "new_family_validations": 2,    # bandit mode only: a family is "new" to it until this many validation looks
        "retire_revisions": 30,
        "retire_evaluations": 2000,
        "retire_dsr_below": 0.05,       # trial-adjusted evidence below the line (after `retire_min_validations`)
        "retire_min_validations": 6,
        # A version is validated only after its 1.5x-stress Train robustness run came back with a profit (Sept 26).
        "require_robustness": True,
        # THE DRIFT SCREEN (Sept 27, `evidence.drift_screen`): a version is validated only when its Train drift-adjusted
        # alpha (the daily P&L net of the root's own daily move at the version's average exposure, a year at a time) has a
        # pooled t of at least `drift_min_t` and is positive in `drift_years_positive` Train years (null: every Train year but
        # one); the gate refuses a look at a version that fails it. Off only by JSON false. A version whose Train run predates
        # the figures waits for one Train run again (the researcher queues it with its robustness runs).
        "drift_screen": True,
        "drift_min_t": 1.0,
        "drift_years_positive": None,
        "fork_min_t": 1.0,              # a family forks when its validation t is at least this and it is in the top
        "fork_top": 3,
        "fork_cooldown_hours": 6,
        # AN IDENTICAL PROGRAM IS VALIDATED ONCE (F1, Oct 3; `Tournament.known_validation`): a version whose program (code,
        # merged params, roots) another family's version already validated on the Gym in use takes that result's verdict:
        # no job, no trial. False validates it again, as before.
        "reuse_validations": True,
    },
    "architect": {
        "every_seconds": 14400,
        "refill_seconds": 3600,         # while fewer than population.start live: hourly, up to the gap (max_refill a pass)
        "max_refill": 12,
        "min_new": 3,
        "max_new": 6,
        "openai_model": "gpt-6-astra",
        "sail_profile": "k3_balanced",
        "max_output_tokens": 12000,
        # The operator's research agenda (swarm.json, no deploy): when non-empty, the last section of every architect
        # request (at most 4,000 characters).
        "agenda": "",
        # THE LOCKED PREAMBLE (Sept 29, 2026): the operator's part of the agenda that no model edits (the verifier, the
        # refuted list, the drift rule, the envelope, the data limits; at most 4,000 characters). Non-empty, the agenda is
        # this text verbatim followed by the strategist's latest accepted WHERE TO LOOK section (league/swarm/strategist.py);
        # empty, or before the strategist's first accepted section, it is `agenda` exactly as before.
        "agenda_locked": "",
        # THE FULL GRAVEYARD (Sept 29, 2026): on the Claude route the architect reads every graveyard row as a digest,
        # the first system block, cached; OpenAI and Sail keep the 20 newest rows (their contexts are small).
        "full_graveyard": True,
        "graveyard_digest_tokens": 100000,   # the digest's budget (809 rows fit whole at 100k; a ladder collapses rows past it)
        "graveyard_digest_tail_share": 0.15, # rows buried since the seal ride uncached after it; past this share it is resealed
        # "5m": the sealed digest is marked for the 5-minute cache only when the strategist's call just wrote it (a lone
        # architect call every 20 minutes would pay the write premium for nothing); "1h": every digest call marks it for
        # the hour (only with `claude.cache_1h`, else as "5m"); "off": never marked.
        "graveyard_digest_ttl": "5m",
        # Refuse a digest-route proposal that names no real graveyard row it differs from (off until the cited rate is known).
        "require_differs": False,
        # THE CLASS CAP (R11-2, Sept 29: 83% of births in an hour were one class, TLT/GLD/SLV straddles): at most this many
        # living families of one mechanism class (structure x root group, the strategist's `mechanism_class`); `admit`
        # refuses births past it and the request names the full classes. 0 or null turns it off.
        "max_alive_per_class": 12,
        # THE CELL'S YIELD (H2, Oct 1; league/swarm/cards.py): null keeps the card check as it was (every mechanism-verdict
        # row needs a rebirth claim). {"min_births": N, "floor": F, "lookback_days": D} (or true: 30, 0.10, 7) opens a cell
        # unless its settled births over D days number at least N with a Wilson 95% upper bound on their drift-pass share
        # below F; in an open cell a card that matches only self-refuted and drift rows needs no claim.
        "cell_yield": None,
        # The REFUTED CELLS list up to this many rows a claim may name in each cell where one can be needed (0: off; at
        # most 12): ids and the inputs each read, no figure.
        "claimable_rows": 0,
        # The rebirths one cell may bear in `rebirth_window_days` (7; cards.py reads 3 when the key is absent). policy.json
        # holds the House's value: 6 from Oct 1, 12 from F1 (Oct 3: 16 of the 41 cells that need a claim were at 6 of 6).
        "max_rebirths_per_cell": 3,
    },
    # THE STRATEGIST (Sept 29, 2026; league/swarm/strategist.py): Claude reads the whole graveyard digest, the board, the
    # Validation check-failure counts and the day's births and retirements, and writes only the agenda's WHERE TO LOOK
    # section (the locked preamble is `architect.agenda_locked`, never edited by a model). It runs just before an
    # architect pass that has room to add families, at most every `every_seconds`, and only while `agenda_locked` is set.
    # A validator rejects any section that talks of money, real money, the envelope, changing a threshold or giving a
    # rule a new state (paused, advisory ...), a numeric rule, 2025, the holdout or the Validation period in any words,
    # the operator, overriding the preamble, reviving a refuted idea, or carries non-ASCII; a rejection goes back once
    # with its reasons (`repair_turns`), and a final rejection or any failure keeps the last accepted section. The
    # architect reads the section quoted under a header that says it changes nothing. Its Claude line is `claude.role_usd_day["strategist"]`; Sail (`sail_profile`,
    # `sail_usd_day`) answers when Claude cannot.
    "strategist": {
        "enabled": True,
        "every_seconds": 10800,
        "max_chars": 1600,              # the section's cap ("about 1,500"); the code's ceiling is 2,000
        "min_cites": 3,                 # graveyard or family ids the answer must cite
        "sail_profile": "k3_balanced",
        "sail_usd_day": 1.0,
        "max_output_tokens": 12000,     # Sail only; Claude uses claude.max_tokens
        # A rejected answer goes back once with the validator's reasons (at most 2); the repair reads the digest's cache entry.
        "repair_turns": 1,
        # THE GYM'S ROOTS (F1, Oct 3; `strategist.foreign_roots`): a section that names a ticker outside `gym.roots`, as a
        # signal or as the traded root, is refused. False turns the rule off.
        "gym_roots_only": True,
    },
    "gate": {
        "review_openai_model": "gpt-6-sol",
        "review_sail_profile": "pro_balanced",
        "review_max_output_tokens": 6000,
        "review_usd_day": 1.0,          # a family's reviews and audits a day, on their own fuse
        "every_seconds": 300,
        # The incubator's review and audit (`gate.Gate.incubator_reviews`, release B2): versions read a gate round, 0 to 8
        # (0: none). Never a holdout look; the gate's reviewer and auditor, on their own tries and their own daily fuse
        # (desk "<family>:incubator", `review_usd_day` a day), so the gate's own are untouched.
        "incubator_reviews": 2,
        "gate_box_idle_sleep_seconds": 300,
        # THE LOOK HOLDS (L6(b) and L6(c), the owner's approval of Oct 2, 2026; `gate.Gate.look_hold`): the gate holds a
        # holdout look (no look, no review or audit, no sealed read) at a long-delta version whose Train drift share is at
        # least `drift_share`, or whose expected holdout power at the next look's Holm level is below `min_power`. Each
        # null turns that hold off (rollback); "look_holds": null turns both off. A value that is not a number from 0 to 1
        # is read as its default: a brake is never misread as off.
        "look_holds": {"drift_share": 0.25, "min_power": 0.30},
    },
    "forward": {
        "every_seconds": 3600,          # look for a new forward day on the gate image this often
    },
    "guard": {
        "every_seconds": 180,
        # The House's own burn a day. The new House box burns ~$0.25-0.75 a day (Sail bills measured use), so the line is
        # 2 x 1.0 + 30 = $32. `measured_burn` true would use Sail's 24-hour spend less the swarm's instead (it counts
        # every other box too, and for a day holds a stopped House's history: on Sept 26 that read ~$31 a day).
        "house_burn_usd_day": 1.0,
        "measured_burn": False,
        "margin_usd": 30.0,             # scale to zero below 2 x the House's daily burn + this
        # EVEN PACING (Oct 8, 2026): hold new research while today's Sail research runs ahead of the day's budget pro rata,
        # with `pace_slack` of a day's share allowed ahead (guard.py): research spreads over 24 h instead of holding at noon.
        "pace_day": True,
        "pace_slack": 0.05,
        # The daily Sail cap is THE BUDGET's (league/ops/budget.py: the `budget` block `load` sets): the trio (`burst_cap_usd`,
        # `burst_until`, `after_burst_usd_day`) is gone (LTCM v3), and a swarm.json that still names it changes nothing.
        "openai_cap_usd": 150.0,        # OpenAI for the burst, and only while the gateway's month has room
        # Never spend the gateway month below this: the House's own roles need its last dollars, and at T0 the month had
        # $10.89 left (effectively none until the owner funds it), so the swarm spends OpenAI only after a raise.
        "openai_reserve_usd": 25.0,
    },
    # The House's live path's switches (league/live/step.py `OptionsLive.switches`; the sprint, B4, Sept 26, 2026):
    # these defaults, overlaid by <state>/swarm.json "live" read DIRECTLY by the live path each minute (never
    # config.json), so they work in the no-deploy window. A switch is on only while it is JSON true; a swarm.json that
    # is not a JSON object turns observe, calibration, the House live test and the incubator off. They switch work off
    # or bound it; no money rule lives here (the constitution's).
    "live": {
        # THE PRACTICE LEAGUE (the observe band; Sept 29, 2026): every alive Gym-band family with a validated version, or
        # an eligible Train version (`observe_train`), trades shadow (never real) on live quotes, validated first (by
        # validation t), then Train (by Train score). Two caps: instances and the distinct roots they read (every root is
        # read every minute, about 1.1-1.5 data calls each; measured on the House Sept 29).
        "observe": True,
        "observe_max": 48,              # at most this many observe instances
        "observe_train": True,          # admit families with an eligible Train version and no validated one
        "observe_roots_max": 24,        # at most this many distinct roots across the observe instances (1-128)
        # The minute's data calls before observe reads stop (10-200): equal to the step's own DEFAULTS (a test pins
        # them), room for 24 roots at the 3-page cap and a held read each after the real phase's 20 (v3).
        "observe_read_calls": 120,
        "calibration": False,           # the D3 real-fill round trips: ON only by swarm.json {"live": {"calibration": true}}
        "calibration_samples": 30,      # a symbol's round trips stop once its open-at-mid cell has this many samples
        # The House live test (league/live/house_test.py): ON only by swarm.json {"live": {"house_test": true}}, and then
        # only with real money on, the grant, the paper proof and its private program verified. Off: exits only.
        "house_test": False,
        # THE INCUBATOR (league/live/incubator.py; the owner's terms of Sept 29-30, 2026; the money table's
        # `options_money.incubator`): one lot of real money for a family whose practice cohort passed its pre-registered
        # first look, Train and drift and its review and audit; never evidence, never a promotion. ON only by swarm.json
        # {"live": {"incubator": true}} (JSON true; any other value reads off and is alerted once), switched on outside a
        # session after the ratification and the site's label. Off: its instances go to exits only and their working
        # opens are cancelled within a minute; first looks are still recorded.
        "incubator": False,
    },
    # THE PRACTICE LEAGUE'S FEEDBACK (Sept 29, 2026; league/swarm/practice.py): the practice record (shadow trades on
    # live quotes under the Gym's fill rules, the House's private observe.sqlite) as a RESEARCH signal, never evidence:
    # the strategist's PRACTICE table, the architect's PRACTICE BY CLASS lines and the allocation share's capped bonus.
    # `feedback` false turns all three off (no deploy). The bonus moves only research attention (the family's allocation
    # weight); it never reaches validation, the gate, the holdout, the bands, the live path or the money table.
    "practice": {
        "feedback": True,
        "sessions": 10,                 # the session days the feedback reads (1-60)
        "bonus": 0.25,                  # a family's largest relative share bonus (0-0.5; 0 turns the bonus off)
        "bonus_total": 0.10,            # the most share the bonus moves in all (0-0.2)
        "min_trades": 3,                # program-closed practice trades before any bonus (1-50)
    },
    # Claude through the gateway (Sept 26, 2026, the swarm sprint; league/claude.py). The gateway's CLAUDE_USD (the owner's
    # funded total) is the hard line; `usd_cap` is the swarm's own Claude line inside it and `reserve_usd` is never
    # spent (the House's post-mortem). `roles` are the calls Claude answers first; removing one routes it as before. Every
    # role asks (Sept 29, 2026), so adding "rewrite" (the researcher's stall rewrite, else its Sail profile) or "review"
    # (the gate's program review, else GPT-6 Sol, else Sail) in swarm.json routes it to Claude with no deploy.
    # `role_usd_day` {role: usd} is a role's own Claude line a UTC day, holds included: a call that would pass it skips
    # Claude for the role's next route (OpenAI when it has one, else Sail). A call counts on the UTC day its hold was
    # booked, even when it settles after midnight. No entry is no extra line; e.g. {"rewrite": 10} keeps rewrites from
    # draining the funded total. `role_model` {role: model id} answers a role on its own Claude model instead of `model`
    # (it must be priced in league/claude.py MODEL_CEILINGS and the gateway's CLAUDE_MODELS, else the role falls to its
    # next route): with "review" and "audit" both in `roles`, e.g. {"review": "claude-sonnet-5-5"} keeps the gate's two
    # reads on two different models. No entry is `model`. "researcher" (Sept 29, 2026) is the top band's research cycles
    # on Claude (`researcher.claude_*`): on Claude Sonnet 5.5 (its `role_model`), within $100 a UTC day (its
    # `role_usd_day`); removing the role from `roles` turns the band off. "postmortem" (LTCM v3) is the House's weekly
    # post-mortem (league/ops/postmortem.py): Claude Opus 5.5 (its `role_model`), within $1 a UTC day (one run a week, so
    # the run's cap, at `max_tokens` 16,000 at most); it alone may spend `reserve_usd`, kept for it. The job adds the role
    # to its own copy of `roles` (a swarm.json that replaces the list still serves it): its off switch is ops.json
    # `postmortem.model: false`, which leaves the report unwritten by the model (the facts are still written).
    "claude": {
        "model": "claude-opus-5-5",
        "effort": "high",
        "usd_cap": 100.0,
        "reserve_usd": 5.0,
        "max_tokens": 16000,            # thinking and the answer together (up to 32,000 streamed; 16,000 not)
        "stream": True,                 # server-sent events through the gateway: no hop waits 100 s in silence (HTTP 524)
        "roles": ["architect", "audit", "diagnostician", "postmortem", "researcher", "strategist"],
        # The strategist's own line (Sept 29, 2026): its run is skipped, with no call, when the next call could pass it.
        "role_usd_day": {"postmortem": 1.0, "researcher": 100.0, "strategist": 4.0},
        "role_model": {"postmortem": "claude-opus-5-5", "researcher": "claude-sonnet-5-5"},
        # The 1-hour cache marker (Sept 29, 2026): true only once the gateway admits `ttl: "1h"` (today it refuses it
        # with a 400, which would drop the call to its next route). Off, no call ever sends one.
        "cache_1h": False,
        # A role's own Claude effort (R11-3) {role: low | medium | high | xhigh | max}, used when the caller names none;
        # `effort` stays every other role's (the gate's reads keep "high"). E.g. {"architect": "medium"}: its output ran
        # 20-29k tokens a pass whatever it bore, and 6 of 28 Sonnet passes were cut at the 32k cap on Sept 29.
        "role_effort": {},
    },
    # The diagnostician (league/swarm/diagnostician.py): Claude reads a family that is stuck or nearly there and rewrites
    # its mechanism or writes its lesson. Eligible: `min_validations` validations without passing, or the latest
    # validation passing at least `near_miss_checks` of the line's checks; at most once a family every `family_hours`,
    # within `usd_day` of Claude spend a day.
    "diagnostician": {
        "enabled": True,
        "every_seconds": 300,
        "per_round": 2,
        "family_hours": 6.0,
        "usd_day": 15.0,
        "min_validations": 2,
        "near_miss_checks": 6,
        "structured": True,             # a JSON-schema answer (structured outputs); false reads the JSON from the text
        "retry_truncated": True,        # one retry at medium effort after an answer cut off at max_tokens
    },
    # THE RESEARCH LIBRARY (Sept 29, 2026; league/swarm/library.py, the gateway's GET /v1/research/*): arXiv papers posted
    # by the end of 2024, for the Claude researchers (the `literature` tool) and a retrieved block for the architect and
    # the strategist. Off until `enabled` is true in swarm.json, after the gateway that carries it is deployed. The lines
    # count calls a UTC day from the `swarm.research` events: `requests_day` every role together (the line the spend
    # report names), `family_requests_day` a family, `cycle_calls` a research cycle; a call they refuse is a plain refusal.
    # `min_seconds_left`: no call with less of the cycle left. `search_max` items a search, `search_abstract_chars` of each
    # abstract and `read_chars` of text a read reach the model. `retrieval`: the architect's searches (`queries`, each
    # `per_query` items, `items` kept, within `seconds`), kept `ttl_seconds`; `seed_queries` are searched four at a time in
    # rotation until the strategist's accepted section names its own `library_queries`.
    "research": {
        "enabled": False,
        "requests_day": 300,
        "family_requests_day": 12,
        "cycle_calls": 2,
        "min_seconds_left": 47,
        "search_max": 5,
        "search_abstract_chars": 900,
        "read_chars": 8000,
        "timeout_seconds": 60,
        "retrieval": {"queries": 4, "per_query": 4, "items": 8, "abstract_chars": 900, "seconds": 60, "ttl_seconds": 10800},
        "seed_queries": ["variance risk premium index options", "zero days to expiration options",
                         "overnight returns index options", "implied volatility term structure predictability",
                         "option order flow informed trading", "dealer gamma hedging intraday",
                         "weekly options volatility risk premium", "volatility skew return predictability"],
    },
    # THE WINDOW FALLBACK (V3-A, Oct 2, 2026; league/swarm/models.py): a one-shot call (`ModelRouter.ask`) on a Sail profile
    # outside the asap window, mapped here to an asap profile, retries once there after a poll timeout, and the window's
    # calls go straight there for an hour (kv `sail_window_stall`). An entry set to null removes it; null turns the map off.
    "sail_fallback": {"k3_balanced": "pro_asap", "pro_balanced": "pro_asap"},
    # The roles whose fallback keeps their MODEL (that model's asap profile, k3_balanced to k3, whatever the map names): the
    # gate's audit is a second model, different from the review's DeepSeek-V4-Pro, on its fallback too. null: none.
    "sail_fallback_same_model": ["audit"],
    "heartbeat_seconds": 20,
    "stale_heartbeat_seconds": 240,     # the House restarts a swarm whose heartbeat is older than this
    "nice": 10,
}


def _merge(base: dict[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (over or {}).items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def parse_train_from(raw: Any, running: dt.date | None = None) -> tuple[dt.date, str | None]:
    """(Train's first day, a note for the operator or None) from a `gym.train_from` value, given the running swarm's span
    (`running`, its store's migrated objective; 2022-01-03 when None): one of `TRAIN_STARTS` is taken; a date in the first
    days of January before that year's first session snaps to it (with a note). Anything else, or no value at all while
    the running span is not 2022-01-03, KEEPS the running span, with a note: a typo or a deleted key never switches Train
    back to 2022 (switching back is `"2022-01-03"`, written out). With the switch off an ignored value is harmless."""
    running = running or TRAIN_CORE_START
    if raw is None:
        if running == TRAIN_CORE_START:
            return TRAIN_CORE_START, None
        return running, (f"gym.train_from is not set: the swarm keeps Train from {running} (set it to \"{TRAIN_CORE_START}\" "
                         "to switch back)")
    day: dt.date | None = None
    if isinstance(raw, dt.date):
        day = raw
    elif isinstance(raw, int) and not isinstance(raw, bool) and raw in TRAIN_STARTS:
        day = dt.date(raw, 1, 1)
    elif isinstance(raw, str):
        try:
            day = dt.date.fromisoformat(raw.strip())
        except ValueError:
            day = None
    if day is not None and day.year in TRAIN_STARTS and day.month == 1 and day <= TRAIN_STARTS[day.year]:
        start = TRAIN_STARTS[day.year]
        note = None if day == start else f"gym.train_from {raw!r} is before {day.year}'s first session: Train starts {start}"
        return start, note
    return running, (f"gym.train_from {raw!r} is not a Train start ({', '.join(d.isoformat() for d in TRAIN_STARTS.values())}): "
                     f"ignored, the swarm keeps Train from {running}")


def _raw(settings: Mapping[str, Any] | None) -> Any:
    return ((settings or {}).get("gym") or {}).get("train_from")


def train_from(settings: Mapping[str, Any] | None, running: dt.date | None = None) -> dt.date:
    """The first Train day `gym.train_from` asks for (`parse_train_from`, given the running span): what the swarm's next
    start migrates to."""
    return parse_train_from(_raw(settings), running)[0]


def train_from_note(settings: Mapping[str, Any] | None, running: dt.date | None = None) -> str | None:
    """Why `gym.train_from` was snapped or ignored (None: it was taken as written)."""
    return parse_train_from(_raw(settings), running)[1]


def objective_span(objective: Any) -> dt.date:
    """The first Train day of a stored objective name (`researcher.objective_for`: "worst-train-year-v1@2020-01-02");
    2022-01-03 for the base name, none, or anything unreadable. The running swarm's span is its store's objective's."""
    _, _, tail = str(objective or "").partition("@")
    try:
        day = dt.date.fromisoformat(tail)
    except ValueError:
        return TRAIN_CORE_START
    return day if day in TRAIN_STARTS.values() else TRAIN_CORE_START


def span_years(span: dt.date | None) -> tuple[int, ...]:
    """The calendar years Train covers from `span` (2022-01-03 when None) to 2024."""
    return tuple(range((span or TRAIN_CORE_START).year, TRAIN_END.year + 1))


def train_years(settings: Mapping[str, Any] | None) -> tuple[int, ...]:
    """The calendar years Train covers under `gym.train_from`: (2022, 2023, 2024) by default, 2020-2024 or 2017-2024
    with it on."""
    return span_years(train_from(settings))


def _explicit(settings: Mapping[str, Any] | None, name: str) -> float | None:
    value = ((settings or {}).get("gym") or {}).get(name)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def train_split(settings: Mapping[str, Any] | None, span: dt.date | None = None) -> int:
    """The Train split: `gym.train_split` when the operator set it, else 8 per three years of Train rounded up (8 over
    2022-2024; 16 over 2020-2024: two full waves on 8 workers, segments shorter than today's; 24 over 2017-2024)."""
    explicit = _explicit(settings, "train_split")
    if explicit is not None:
        return max(1, int(explicit))
    return BASE_TRAIN_SPLIT * max(1, math.ceil(len(span_years(span)) / 3))


def run_timeout(settings: Mapping[str, Any] | None, span: dt.date | None = None) -> float:
    """A Gym batch's time limit in seconds: `gym.run_timeout_seconds` when the operator set it, else 900 s scaled by the
    Train years a Train batch covers (`span`; None: any other window, 900): 1500 over five years, 2400 over eight."""
    explicit = _explicit(settings, "run_timeout_seconds")
    if explicit is not None:
        return explicit
    return float(round(BASE_RUN_TIMEOUT * max(3, len(span_years(span))) / 3))


#: The prompts' words for Train's span, as written for the default (2022-2024).
_SPAN_TEXT = (("Train 2022-2024", "Train {a}-{b}"), ("Train (2022-2024)", "Train ({a}-{b})"),
              ("earn in 2022, 2023 and 2024 alike", "earn in {years} alike"))


def train_span_text(text: str, span: dt.date | None) -> str:
    """A prompt with Train's span (the running swarm's, `objective_span`): `text` itself (the same string) while Train
    is 2022-2024."""
    years = span_years(span)
    if years == (2022, 2023, 2024):
        return text
    listed = ", ".join(str(y) for y in years[:-1]) + f" and {years[-1]}"
    for old, new in _SPAN_TEXT:
        text = text.replace(old, new.format(a=years[0], b=years[-1], years=listed))
    return text


#: The repo's settings layer (SETTINGS AS CODE in the module docstring).
POLICY_PATH = REPO / "league" / "swarm" / "policy.json"
#: The owner's switches: read from `<root>/swarm.json` only, never from policy.json (the live path reads `live` from
#: swarm.json directly, league/live/step.py).
OWNER_KEYS = ("enabled", "live")


def read_policy(path: str | Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(the layer, its status) from policy.json (`POLICY_PATH` by default). The status is {"state": "absent" | "ok" |
    "malformed", "why": ..., "ignored": [owner keys left out]}; an absent or malformed file is an empty layer."""
    path = Path(path) if path is not None else POLICY_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, {"state": "absent", "why": None, "ignored": []}
    except (OSError, ValueError) as exc:
        return {}, {"state": "malformed", "why": f"{type(exc).__name__}: {str(exc)[:160]}", "ignored": []}
    return policy_layer(raw)


#: The blocks of DEFAULTS a policy may set to null (each documented as "null turns it off"); every other block of DEFAULTS
#: must stay an object in policy.json.
POLICY_NULLABLE = frozenset({"sail_fallback", "gate.look_holds"})


def policy_shape(raw: Mapping[str, Any], defaults: Mapping[str, Any] | None = None, prefix: str = "") -> list[str]:
    """The paths where a policy document's shape breaks DEFAULTS': a block of DEFAULTS (an object) set to anything but an
    object (null only at `POLICY_NULLABLE`), or an object where DEFAULTS holds a plain value. A key DEFAULTS lacks, or one
    whose default is null, is not checked; nor are notes ("_")."""
    defaults = DEFAULTS if defaults is None else defaults
    bad: list[str] = []
    for key, value in raw.items():
        if str(key).startswith("_") or key not in defaults:
            continue
        path, default = f"{prefix}{key}", defaults[key]
        if isinstance(default, Mapping):
            if isinstance(value, Mapping):
                bad += policy_shape(value, default, f"{path}.")
            elif not (value is None and path in POLICY_NULLABLE):
                bad.append(path)
        elif default is not None and isinstance(value, Mapping):
            bad.append(path)
    return bad


def policy_layer(raw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """(the layer, its status) from a parsed policy document: an object without its owner keys, else an empty layer. A
    document whose shape breaks DEFAULTS' (`policy_shape`: e.g. `"gym": null`, `"researcher": 0.4`) is malformed: the
    whole layer is dropped and the loop alerts, rather than every round failing on the block it replaced."""
    if not isinstance(raw, Mapping):
        return {}, {"state": "malformed", "why": f"not a JSON object ({type(raw).__name__})", "ignored": []}
    bad = policy_shape({k: v for k, v in raw.items() if k not in OWNER_KEYS})  # those are ignored, never read
    if bad:
        return {}, {"state": "malformed", "why": f"not the shape of the defaults at {', '.join(sorted(bad)[:8])}", "ignored": []}
    ignored = sorted(k for k in raw if k in OWNER_KEYS)
    return {k: v for k, v in raw.items() if k not in OWNER_KEYS}, {"state": "ok", "why": None, "ignored": ignored}


def load(root: str | Path | None = None, *, config: Mapping[str, Any] | None = None,
         policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The swarm's settings: DEFAULTS < config.json "swarm" (and its "gym" block into "gym") < policy.json (`policy`, a
    parsed document, in place of the repo's file) < <root>/swarm.json, then, with a state root, THE BUDGET tighten-only
    (`budget_overlay`: <root>/budget.json, else the floor). `_policy` says how the policy layer was read. Without a root
    (tests, tools) there is no budget block: the Sail guard and the router then read the budget themselves, from their
    store root's budget.json, the floor when there is none (settings without the block never lift the budget)."""
    if config is None:
        try:
            config = json.loads((REPO / "league" / "config.json").read_text())
        except (OSError, ValueError):
            config = {}
    out = _merge(DEFAULTS, config.get("swarm") or {})
    out["gym"] = _merge(out["gym"], config.get("gym") or {})
    layer, status = read_policy() if policy is None else policy_layer(policy)
    out = _merge(out, layer)
    out["_policy"] = status
    if root is not None:
        path = Path(root) / "swarm.json"
        try:
            local = json.loads(path.read_text())
        except (OSError, ValueError):
            local = {}
        if isinstance(local, Mapping):
            out = _merge(out, local)
        try:
            named = out["gym"].get("gate_checkpoint")
        except Exception:  # noqa: BLE001 - a malformed "gym" block: no gate to stand in for
            named = None
        try:
            ready = json.loads((Path(root) / "gym-forward.json").read_text())
            day = dt.date.fromisoformat(ready["day"])
            at = dt.datetime.fromisoformat(ready["ready_at"].replace("Z", "+00:00"))
            checkpoint = ready["gate_checkpoint"]
            valid = (ready.get("schema") == 1 and str(day) == ready["day"] and at.tzinfo is not None
                     and day < at.date() and re.fullmatch(r"sbcp_[A-Za-z0-9-]+", checkpoint)
                     and isinstance(ready.get("roots"), list) and bool(ready["roots"])
                     and all(isinstance(r, str) and re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", r) for r in ready["roots"]))
            if named:
                why = ready_refusal(root, ready, named, out["gym"].get("roots")) if valid else "the ready file is malformed"
                if why is None:
                    out["gym"]["gate_checkpoint"] = checkpoint
                    out["forward"]["ready"] = ready
                else:
                    out["forward"]["ready_ignored"] = {"why": why, "day": str(ready.get("day")),
                                                       "gate_checkpoint": str(checkpoint), "named": named}
        except FileNotFoundError:
            pass
        except Exception as error:  # noqa: BLE001 - THE CHAIN'S RULE: a ready file that cannot be read never moves the gate
            try:
                if named:
                    out["gym"]["gate_checkpoint"] = named
                    out["forward"].pop("ready", None)
                    out["forward"]["ready_ignored"] = {"why": f"the ready file cannot be read ({type(error).__name__})",
                                                       "named": named}
            except Exception:  # noqa: BLE001 - a malformed "forward" block: the settings as merged
                pass
        budget_overlay(out, root)
    return out


def budget_overlay(out: dict[str, Any], root: str | Path) -> dict[str, Any]:
    """THE BUDGET, last and tighten-only (league/ops/budget.py `overlay`): `<root>/budget.json`'s research dollars a day
    cap the spend knobs and become the `budget` block the Sail guard and the router read; no usable file is the floor, and
    a stale one is never looser than the floor. If the rule itself cannot run, nothing is spent: a budget of zero on both
    meters, its `read` false (no reading of the rule: the Sail guard names that brake apart from the budget's own)."""
    try:
        from ..ops import budget as budget_mod

        return budget_mod.overlay(out, root)
    except Exception as exc:  # noqa: BLE001 - FAIL CLOSED: no rule, no research spend
        out["budget"] = {"source": "unavailable", "why": f"the budget rule could not run ({type(exc).__name__})", "at": None,
                         "state": "no research (the budget rule could not run)", "sail_usd_day": 0.0, "claude_usd_day": 0.0,
                         "fixed_sail_usd_day": None, "read": False}
        return out


def _roots_lacking(held: Any, wanted: Any) -> list[str] | None:
    """The swarm's roots (`wanted`) a gate holds no holdout for (`held`: a list of roots); None when `held` is no list."""
    if not isinstance(held, list) or not all(isinstance(r, str) for r in held):
        return None
    have = {r.upper() for r in held}
    return sorted({str(r).upper() for r in (wanted or [])} - have)


def _instant(text: Any) -> dt.datetime | None:
    """An ISO time (a trailing Z or an offset; a naive one is read as UTC), or None."""
    try:
        at = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo is not None else at.replace(tzinfo=dt.timezone.utc)


def chain_refusal(gate: Mapping[str, Any], checkpoint: Any) -> str | None:
    """THE CHAIN'S RULE, its lineage: why `checkpoint` is not proven to extend the gate image `<root>/data/images.json`
    records as current (`gate`: that file's "gate" block), or None when it is. Proven: one of the image's own checkpoints,
    or a checkpoint the nightly took of it (a `checkpoints` entry) when that entry and every later one name the image as
    their `base`. An entry written before the nightly named its base (before Oct 1, 2026) counts only when it was taken
    after the image was recorded (`at` not before `current.built_at`): `images.py build` and `finish` replace `current`
    without resetting the chain, so an older entry may be another image's (scripts/data/nightly.py refuses to extend
    such a chain, and the swarm refuses a legacy ready file on it)."""
    current = gate.get("current") or {}
    images = [c for c in (current.get("checkpoints") or []) if isinstance(c, str)]
    if not images:
        return "data/images.json records no gate image"
    if checkpoint in images:
        return None
    entries = [e for e in (gate.get("checkpoints") or []) if isinstance(e, Mapping)]
    found = next((i for i, e in enumerate(entries) if e.get("id") == checkpoint), None)
    if found is None:
        return f"{checkpoint} is not a checkpoint of the gate image's chain"
    built = _instant(current.get("built_at"))
    for entry in entries[found:]:
        if "base" in entry:
            if entry.get("base") != images[0]:
                return f"the chain's checkpoint {entry.get('id')} extends {entry.get('base')}, not the gate image {images[0]}"
            continue
        taken = _instant(entry.get("at"))
        if built is None or taken is None or taken < built:
            return (f"the chain's checkpoint {entry.get('id')} names no base and was not taken after the gate image "
                    f"{images[0]} was recorded")
    return None


def ready_refusal(root: str | Path, ready: Mapping[str, Any], named: str, roots: Any) -> str | None:
    """THE CHAIN'S RULE (Oct 1, 2026): why the nightly's ready file (`gym-forward.json`) may NOT stand in for the gate
    `swarm.json` names (`named`), or None when it may. The nightly extends the gate image its own record
    (`<root>/data/images.json`) names; that record and `swarm.json` were once apart (the 25-root gate was adopted through
    `swarm.json` alone), and the ready file's checkpoint silently replaced the 25-root gate with a five-root chain.

    A ready file stands only when it extends the named gate and that gate holds a holdout for every root of the swarm
    (`gym.roots`): its `base_checkpoint` (the gate image's first checkpoint, written by the nightly) is `named`, and its
    `holdout_roots` cover `roots`. A LEGACY file (written before the nightly wrote `base_checkpoint`) stands only when
    `<root>/data/images.json` proves the same: its current gate image is `named` (first checkpoint) and its recorded roots
    cover `roots`; the file's checkpoint is its day's recorded checkpoint (`forward_days`), adopted after that image was
    recorded (`built_at`); and `chain_refusal` finds it on that image's chain. It need not be the chain's tip: the
    nightly records a new day's checkpoint before it publishes the day. Anything else, or anything unreadable, is a
    refusal: the swarm then uses `named` itself (no forward days) and the loop raises one alert
    (`Swarm.gate_chain_notice`). `nightly.py stamp-ready` names the gate image in a legacy file that stands."""
    if "base_checkpoint" in ready:
        base = ready.get("base_checkpoint")
        if base != named:
            return f"the forward chain extends {base}, not the gate swarm.json names"
        lacking = _roots_lacking(ready.get("holdout_roots"), roots)
        if lacking is None:
            return "the ready file does not list the roots its gate holds a holdout for"
        if lacking:
            return f"the forward chain's gate holds no holdout for {', '.join(lacking)}"
        return None
    legacy = "a ready file without base_checkpoint"
    try:
        images = json.loads((Path(root) / "data" / "images.json").read_text())
        gate = images.get("gate") or {}
        current = gate.get("current") or {}
        first = (current.get("checkpoints") or [None])[0]
        night = (gate.get("forward_days") or {}).get(str(ready["day"])) or {}
        recorded, adopted = night.get("checkpoint"), _instant(night.get("adopted"))
        built = _instant(current.get("built_at"))
        lineage = chain_refusal(gate, ready["gate_checkpoint"])
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        return f"{legacy}, and no readable data/images.json to prove its chain"
    if first != named:
        return f"{legacy}, and data/images.json's gate is not the gate swarm.json names"
    if ready["gate_checkpoint"] != recorded:
        return f"{legacy} whose checkpoint is not its day's on the named gate's chain"
    if adopted is None or built is None or adopted < built:
        return f"{legacy} whose day was not adopted after the named gate image was recorded"
    if lineage is not None:
        return f"{legacy}: {lineage}"
    lacking = _roots_lacking(current.get("roots"), roots)
    if lacking is None:
        return f"{legacy}, and data/images.json does not list the gate's roots"
    if lacking:
        return f"the forward chain's gate holds no holdout for {', '.join(lacking)}"
    return None


__all__ = ["DEFAULTS", "load", "read_policy", "policy_layer", "policy_shape", "POLICY_PATH", "OWNER_KEYS",
           "POLICY_NULLABLE", "budget_overlay", "chain_refusal", "ready_refusal", "train_from", "train_from_note", "parse_train_from",
           "objective_span", "span_years", "train_years", "train_split", "run_timeout", "train_span_text",
           "TRAIN_CORE_START", "TRAIN_EARLIEST", "TRAIN_END", "TRAIN_STARTS"]
