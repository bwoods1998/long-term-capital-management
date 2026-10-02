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
- `evidence`    the plan's validation and holdout lines, the drift screen, the look holds, the leakage alarm, and the
                Thompson bandit's draws (`allocation.mode` "bandit" only);
- `diagnostics` what a researcher sees of a run (train: a compact table and the drift lines; validation: pass or fail
                and a count of checks, D2a);
- `models`      the model router (Sail's Responses API through `ltcm.provider.Provider`; Claude and OpenAI
                through the gateway only when their budgets have room, else the Sail fallback);
- `pool`        the Gym box pool (forks of the Gym image, sealed; batches day-major via the Gym's
                driver) and the gate's boxes;
- `guard`       the Sail guard (scale to zero before the House is at risk; the burst caps);
- `funding`     funding cliffs and Claude fallbacks, said ahead as deduped `swarm.status` alerts;
- `researcher`  the inner loop (revise -> run -> read -> revise) with its seven tools;
- `claude_research` the top band's research cycles on Claude Sonnet 5.5 (Sept 29, 2026): the tool and
                conversation adapter, the input checks and the append-only session; a Sail fallback;
- `preflight`   a program's synthetic sessions in the decider's sandbox before a Train run is spent;
- `library`     THE RESEARCH LIBRARY (Sept 29, 2026): arXiv papers posted by the end of 2024, through the
                gateway's `/v1/research/*` (which enforces the date rule; the House checks every answer again): the
                Claude researchers' `literature` tool and the architect's and strategist's retrieved block;
- `inputs`      the operator's audited Train input metadata, a prompt block for the architect and researchers;
- `tournament`  the hourly tournament: validation runs, the allocation, forks, retirements, the cohort keep, the
                leaderboard;
- `allocation`  THE ALLOCATOR (Release B): research share by expected information value, the turns, the concurrency and
                the architect's birth quota;
- `evaluator`   evaluator adoption: derived views bound to the Gym image, bundle and execution fingerprint;
- `gate`        the program review, the holdout look, the Candidate band or a recorded refusal;
- `architect`   every `architect.every_seconds` (four hours by default), new families from the leaderboard, the
                graveyard and the gaps;
- `cards`       family cards: the terms a family is born under, and the card-based rebirth refusal;
- `mechanism`   the pre-registered mechanism test (the signal against its card's ablation);
- `strategist`  Claude's WHERE TO LOOK section of the architect's agenda;
- `diagnostician` Claude on a stuck or nearly-there family: a rewritten mechanism, or its lesson;
- `practice`    the practice league's record as a research signal (and the cohort keep's reading of it);
- `incubator`   the incubator's facts for the House: Train-and-drift marks, its reviews and the program bars;
- `bands`       what the House reads (`bands.read(root)`): each family's band and program;
- `public`      the word filters for everything that reaches the public site;
- `progress`    the public promotion checklists;
- `sitefeed`    the site's inputs (schema 2: agents, the Gym's pace, the swarm's compute);
- `hook`        the House's side: `SwarmStep` (supervise, mirror, read, and the side jobs);
- `cleanup`     a stopped swarm's late Gym forks, ended from the House's step;
- `loop`        the process: its scheduler and heartbeat;
- `improvement`, `harness_lanes`, `canary`, `harness_runtime`, `harness_judges/`: the harness improvement loop
                (playbooks/harness-improvement.md);
- `benchmarks`, `evaluator_benchmarks`, `long_single_benchmarks`, `improvement_benchmark`: fixed synthetic benchmarks
                (docs/benchmarks/).
"""

from __future__ import annotations

#: Bumped when the swarm's store layout changes.
SWARM_VERSION = "swarm-1"
DB_NAME = "swarm.sqlite"
PROGRAMS_DIR = "programs"
RUNS_DIR = "swarm-runs"
HEARTBEAT = "swarm.heartbeat"
PID_FILE = "swarm.pid"
LOCK_FILE = "swarm.lock"
LOG_FILE = "swarm.log"
