"""The Gym: where agent-written option programs meet real recorded quotes, fast and honestly.

Built Sept 26, 2026 (the options-swarm run, Wave 3). The plan is `docs/goals/LTCM_OPTIONS_SWARM.md`
("The Gym", "The agent"); the program contract is `league/gym/PROGRAM.md`.

The pieces, each importable on its own so the live path (the House's shadow book and real money)
runs the SAME code on live quotes that the replay runs on recorded ones:

- `store`    the store-v1 reader (per-day Parquet), the windows, and the gate's capability;
- `events`   the static event and rate tables the ENGINE consults (a program sees booleans only);
- `greeks`   vectorized Black-Scholes, implied vol and greeks on the mid;
- `venue`    the venue's rules, fees and ticks (one table for the Gym and the live path);
- `safety`   what a program may contain (imports, attributes, date literals);
- `runtime`  loading a program and calling `decide(ctx)` safely (time limits, errors counted);
- `ctx`      building `ctx` from plain arrays for one minute (a replay grid or a live chain read);
- `legs`     resolving a structure intent into legs, a limit, a quantity and a maximum loss;
- `fills`    the fill model (natural by default; calibrated better-than-natural fills keyed by
             contract and minute, never by the program) and the stress mode;
- `engine`   the day-major replay; `results` what a run returns; `batch` the CLI;
  `driver`   the sealed-box driver over Sail's files and exec APIs; `calibrate` the fill model's fit;
  `synth`    a synthetic store for tests and benchmarks (never licensed data).

numpy and pyarrow are needed by the engine (`requirements-gym.txt`); this file imports neither, so
`league.gym` can be imported (and its tests skipped) where they are absent.
"""

#: Bumped whenever the engine's arithmetic changes what a run returns: it is part of every run's hash.
ENGINE_VERSION = "gym-engine-1"
#: The store layout this engine reads.
STORE_VERSION = "store-v1"
