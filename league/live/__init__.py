"""The live options path: the House's minute of live chains, the shadow book, the paper proof and real money.

Built Sept 26, 2026 (the options-swarm run, Wave 5; the plan `docs/goals/LTCM_OPTIONS_SWARM.md`, "The venue", "Money",
"Wave 5"). `House.options_live` is `step.OptionsLive` (`league/service.py` builds it when `config.json` `live.enabled`).

- `step`      the minute: families and instances, chain reads, the shadow book, the real account, the decider batch;
- `money`     the constitution's `options_money` table applied: bands, sizing by maximum loss, the stops;
- `real`      the real book and its order path (client ids written before sending, one stream a contract, the
              order count, reconciliation, broken structures);
- `shadow`    the shadow book: the Gym's own `engine.Account` stepped over live grids, one minute behind;
- `chains`    live chains as the Gym's day grids (`LiveChain`, `LiveDay`), XSP/SPXW by put-call parity;
- `decider`   agent programs in a child process with no secrets and hard time limits;
- `paper`     the practice account's multi-leg round trip, before the first real order;
- `venue`     the gateway's reads and writes (the Brokerage Account, the practice account, market data);
- `families`  the swarm's bands and forward records; `state` the live state on disk; `__main__` the owner's commands.

Python 3.11 with numpy only (the House box has no pyarrow).
"""
