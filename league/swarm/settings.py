"""The swarm's settings: defaults, overlaid by `league/config.json` ("gym" and "swarm") and then by
`<root>/swarm.json` (the operator's file on the box: a change there needs no deploy; the process
re-reads it every loop).

The EVIDENCE LINES are not settings: they are the plan's, in `evidence.py`, and loosening one is the
owner's decision. Everything here is throughput and money: how many, how often, how much.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[2]

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    # The population (plan: 48 at the start of the training burst, a ceiling of 96, a floor of 16).
    "population": {"start": 48, "ceiling": 96, "floor": 16},
    "researcher": {
        # DeepSeek-V4-Flash at asap for the inner loop. V4.1-Flash (`long_profile`) is for long, well-cached histories:
        # measured Sept 26 at the cache share a trimmed history gets (44-66%), it cost four times V4-Flash a call, so it
        # is off unless `long_history_chars` is lowered.
        "profile": "flash_asap",
        "long_profile": "flash41_asap",
        "long_history_chars": 10 ** 9,
        # One rewrite after a stall of `stall_revisions`: V4-Pro balanced, Kimi-K3 balanced for the top ten; asked in the
        # background (V4-Pro's balanced window took over five minutes on Sept 26), capped and spaced.
        "rewrite_profile": "pro_balanced",
        "top_rewrite_profile": "k3_balanced",
        "top_rewrite_families": 10,
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
        "family_usd_day": 3.0,          # each family's daily model budget (the Provider's desk cap): a fuse
        "floor_usd_day": 150.0,         # every model call of the swarm together, a day (the Provider's floor cap): a fuse
        "idle_seconds": 5,              # between a family's cycles
        "note_every_cycles": 6,         # a public note to the tape at most this often per family
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
        "validation_split": 4,
        "run_timeout_seconds": 900,
        "idle_sleep_seconds": 600,      # a box idle this long sleeps (sleeping boxes cost nothing)
        "box_usd_hour": 0.20,           # a busy l box (Sail bills measured use; $0.12-0.20/h measured Sept 26)
        "remote_root": "/workspace/gym",
        "store_root": "/data/store",
        "python": "/opt/data-venv/bin/python",  # the Gym image is a fork of the data box: its venv has numpy and pyarrow
        "capital": 10000.0,
        "roots": ["SPY", "QQQ", "IWM", "XSP", "SPXW"],
    },
    "tournament": {
        "every_seconds": 3600,
        "explore_share": 0.25,
        "new_family_validations": 2,    # a family is "new" to the bandit until this many validation looks
        "retire_revisions": 30,
        "retire_evaluations": 2000,
        "retire_dsr_below": 0.05,       # trial-adjusted evidence below the line (after `retire_min_validations`)
        "retire_min_validations": 6,
        "fork_min_t": 1.0,              # a family forks when its validation t is at least this and it is in the top
        "fork_top": 3,
        "fork_cooldown_hours": 6,
    },
    "architect": {
        "every_seconds": 14400,
        "min_new": 3,
        "max_new": 6,
        "openai_model": "gpt-6-astra",
        "sail_profile": "k3_balanced",
        "max_output_tokens": 12000,
    },
    "gate": {
        "review_openai_model": "gpt-6-sol",
        "review_sail_profile": "pro_balanced",
        "review_max_output_tokens": 6000,
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
    return out


__all__ = ["DEFAULTS", "load"]
