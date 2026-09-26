"""The swarm: researcher agents that write option programs, train them in the Gym, and earn bands.

Built Sept 26, 2026 (the options-swarm run, Wave 4). The plan is `docs/goals/LTCM_OPTIONS_SWARM.md`
("The agent", "The loops", "Evidence", "Compute"); the program contract the researchers write to is
`league/CONTRACT.md` (taken from the Gym's `league/gym/PROGRAM.md`).

THE PROCESS. The swarm runs as its own process on the House box (`python -m league.swarm run --root
/workspace/state`), niced, beside the House loop. The House's `swarm` step (`hook.SwarmStep`, one line
in `league/service.py`) keeps it running (a heartbeat file; restarted when it dies, hangs or runs an
old release), mirrors its events into the House ledger and reads its bands; the House never blocks on
it, and a swarm crash never stops the trading loop.

ITS STATE. `<root>/swarm.sqlite` (families, program versions, runs, notebooks, the graveyard, holdout
looks, forward records, spend, events) and `<root>/programs/<family>/` (the programs themselves). Neither
is ever in git: the repository is public, and programs are fitted to licensed data. Full Gym results
live under `<root>/swarm-runs/`.

THE PIECES.

- `settings`    defaults and the config blocks (`league/config.json` "swarm"/"gym", `<root>/swarm.json`);
- `store`       the SQLite store (`SwarmStore`) and the program files;
- `seeds`       the 48 founding families (mechanisms re-expressed for the Gym) and their starter programs;
- `evidence`    the plan's validation and holdout lines, the leakage alarm, and the bandit's draws;
- `diagnostics` what a researcher sees of a run (train: a compact table; validation: mean, t, quarters);
- `models`      the model router (Sail's Responses API through `ltcm.provider.Provider`; OpenAI through
                the gateway only when its month has room, else the Sail fallback);
- `pool`        the Gym box pool (forks of the Gym image, sealed; batches day-major via the Gym's
                driver) and the gate's boxes;
- `guard`       the Sail guard (scale to zero before the House is at risk; the burst caps);
- `researcher`  the inner loop (revise -> run -> read -> revise) with its five tools;
- `tournament`  the hourly tournament: validation runs, the bandit, forks, retirements, the leaderboard;
- `gate`        the program review, the holdout look, the Candidate band or a recorded refusal;
- `architect`   every four hours, 3-6 new families from the leaderboard, the graveyard and the gaps;
- `bands`       what the House reads (`bands.read(root)`): each family's band and program;
- `sitefeed`    the site's inputs (schema 2: agents, the Gym's pace) and the tape's words;
- `hook`        the House's side: `SwarmStep` (supervise, mirror, read);
- `loop`        the process: its scheduler and heartbeat.
"""

from __future__ import annotations

#: Bumped when the swarm's store layout changes.
SWARM_VERSION = "swarm-1"
DB_NAME = "swarm.sqlite"
PROGRAMS_DIR = "programs"
RUNS_DIR = "swarm-runs"
HEARTBEAT = "swarm.heartbeat"
PID_FILE = "swarm.pid"
LOG_FILE = "swarm.log"
