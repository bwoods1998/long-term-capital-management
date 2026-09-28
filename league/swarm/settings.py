"""The swarm's settings: defaults, overlaid by `league/config.json` ("gym" and "swarm") and then by
`<root>/swarm.json` (the operator's file on the box: a change there needs no deploy; the process
re-reads it every loop).

The EVIDENCE LINES are not settings: they are the plan's, in `evidence.py`, and loosening one is the
owner's decision. Everything here is throughput and money: how many, how often, how much.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[2]

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    # The population (plan: 48 at the start of the training burst, a ceiling of 96, a floor of 16).
    # `reseed_max`: families a main-loop pass founds from the seeds on untried roots while below the start and the architect
    # is not due (`Swarm.reseed`). Off (0) by default: reseeds fill the gap the architect's refill cadence keys on, so a
    # swarm that reseeds sees the architect every `every_seconds` instead of every `refill_seconds`.
    "population": {"start": 48, "ceiling": 96, "floor": 16, "reseed_max": 0},
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
        # The bandit's top `top_families` by weight run every cycle on a stronger profile at low effort (the sprint, Sept
        # 26); the rest stay on `profile`. Null `top_profile` turns it off. The hourly pace below governs these cycles too.
        "top_profile": "pro_asap",
        "top_reasoning_effort": "low",
        "top_families": 10,
        "top_max_output_tokens": 12000,  # low effort's reasoning (1,800-3,800 tokens measured) and a whole program
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
        "note_every_cycles": 6,         # a public note to the tape at most this often per family
        # The idle rule (R3, Sept 27): a Gym family with this many revisions since its last validation and no eligible
        # Train version (or a best Train score below zero) is dead. It may retire at `population.start` (only
        # `population.floor` holds it), and the tournament retires it if it does not. 0 or null turns the rule off.
        "retire_idle_revisions": 40,
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
        "train_split": 8,
        "validation_split": 1,          # Validation, holdout and forward run whole (the Gym refuses to split them)
        "run_timeout_seconds": 900,
        "idle_sleep_seconds": 600,      # a box idle this long sleeps (sleeping boxes cost nothing)
        "box_usd_hour": 0.20,           # a busy l box (Sail bills measured use; $0.12-0.20/h measured Sept 26)
        "remote_root": "/workspace/gym",
        "store_root": "/data/store",
        "python": "/opt/data-venv/bin/python",  # the Gym image is a fork of the data box: its venv has numpy and pyarrow
        "capital": 10000.0,
        "roots": ["SPY", "QQQ", "IWM", "XSP", "SPXW"],
    },
    # A robustness run waiting this long (its 1.5x run; the mid run twice as long) takes a Train job's priority (aging).
    "pool": {"robust_age_seconds": 600},
    "tournament": {
        "every_seconds": 3600,
        "explore_share": 0.25,
        "new_family_validations": 2,    # a family is "new" to the bandit until this many validation looks
        "retire_revisions": 30,
        "retire_evaluations": 2000,
        "retire_dsr_below": 0.05,       # trial-adjusted evidence below the line (after `retire_min_validations`)
        "retire_min_validations": 6,
        # A version is validated only after its 1.5x-stress Train robustness run came back with a profit (Sept 26).
        "require_robustness": True,
        "fork_min_t": 1.0,              # a family forks when its validation t is at least this and it is in the top
        "fork_top": 3,
        "fork_cooldown_hours": 6,
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
    },
    "gate": {
        "review_openai_model": "gpt-6-sol",
        "review_sail_profile": "pro_balanced",
        "review_max_output_tokens": 6000,
        "review_usd_day": 1.0,          # a family's reviews and audits a day, on their own fuse
        "every_seconds": 300,
        "gate_box_idle_sleep_seconds": 300,
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
        "burst_cap_usd": 350.0,         # Sail spend for the training burst
        "burst_until": "2026-09-28T13:30:00Z",
        "after_burst_usd_day": 12.0,    # Sail a day after Monday while Net is not positive
        "openai_cap_usd": 150.0,        # OpenAI for the burst, and only while the gateway's month has room
        # Never spend the gateway month below this: the House's own roles need its last dollars, and at T0 the month had
        # $10.89 left (effectively none until the owner funds it), so the swarm spends OpenAI only after a raise.
        "openai_reserve_usd": 25.0,
    },
    # The House's live path's switches (league/live/step.py `OptionsLive.switches`; the sprint, B4, Sept 26, 2026): these
    # defaults, overlaid by <state>/swarm.json "live" read DIRECTLY by the live path each minute (never config.json), so
    # they work in the no-deploy window. A switch is on only while it is JSON true; a swarm.json that is not a JSON object
    # turns observe and calibration off. They switch work off or bound it; no money rule lives here (the constitution's).
    "live": {
        "observe": True,                # every alive Gym-band family with a validated version trades shadow (never real)
        "observe_max": 48,              # at most this many observe instances (the likeliest by validation t first)
        "calibration": False,           # the D3 real-fill round trips: ON only by swarm.json {"live": {"calibration": true}}
        "calibration_samples": 30,      # a symbol's round trips stop once its open-at-mid cell has this many samples
    },
    # Claude through the gateway (Sept 26, 2026, the swarm sprint; league/claude.py). The gateway's CLAUDE_USD ($100, the
    # owner's funded total) is the hard line; `usd_cap` is the swarm's own Claude line inside it and `reserve_usd` is never
    # spent (the House's post-mortem). `roles` are the calls Claude answers first; removing one routes it as before.
    "claude": {
        "model": "claude-opus-5-5",
        "effort": "high",
        "usd_cap": 100.0,
        "reserve_usd": 5.0,
        "max_tokens": 16000,            # thinking and the answer together (up to 32,000 streamed; 16,000 not)
        "stream": True,                 # server-sent events through the gateway: no hop waits 100 s in silence (HTTP 524)
        "roles": ["architect", "audit", "diagnostician"],
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


def load(root: str | Path | None = None, *, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The swarm's settings: DEFAULTS < config.json "swarm" (and its "gym" block into "gym") < <root>/swarm.json."""
    if config is None:
        try:
            config = json.loads((REPO / "league" / "config.json").read_text())
        except (OSError, ValueError):
            config = {}
    out = _merge(DEFAULTS, config.get("swarm") or {})
    out["gym"] = _merge(out["gym"], config.get("gym") or {})
    if root is not None:
        path = Path(root) / "swarm.json"
        try:
            local = json.loads(path.read_text())
        except (OSError, ValueError):
            local = {}
        if isinstance(local, Mapping):
            out = _merge(out, local)
        try:
            ready = json.loads((Path(root) / "gym-forward.json").read_text())
            day = dt.date.fromisoformat(ready["day"])
            at = dt.datetime.fromisoformat(ready["ready_at"].replace("Z", "+00:00"))
            checkpoint = ready["gate_checkpoint"]
            valid = (ready.get("schema") == 1 and str(day) == ready["day"] and at.tzinfo is not None
                     and day < at.date() and re.fullmatch(r"sbcp_[A-Za-z0-9-]+", checkpoint)
                     and isinstance(ready.get("roots"), list) and bool(ready["roots"])
                     and all(isinstance(r, str) and re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", r) for r in ready["roots"]))
            if valid and out["gym"].get("gate_checkpoint"):
                out["gym"]["gate_checkpoint"] = checkpoint
                out["forward"]["ready"] = ready
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
    return out


__all__ = ["DEFAULTS", "load"]
