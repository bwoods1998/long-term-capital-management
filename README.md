# Long Term Capital Management

An options research swarm with one goal: real option returns greater than every input cost. Researchers write private programs, test them on recorded market data, and earn access to live shadow or real capital through measured evidence. A profitable backtest is not a promise of live profit.

The House supervises three components:

- **Gym:** the same deterministic program contract and structure arithmetic on historical quotes and live chains. Train teaches; Validation selects; a separate sealed gate holds the holdout.
- **Swarm:** a population of mechanism families, private notebooks and programs, counted trials, a tournament and evidence bands. Researchers receive their own historical results, never holdout rows.
- **Live path:** Candidate shadow accounts, a paper account that proves order routing, and a separately authorized real book. It owns reconciliation, exits, maximum-loss sizing, stops and durable order identities.

The external gateway holds brokerage and OpenAI credentials, independently bounds order risk and spend, and exposes the owner's kill switch. The House has only the gateway, Sail and site-publishing tokens. Data boxes never receive a gateway token; Gym and gate boxes have no network or credentials.

## The number

The site's **Profit** is all real-options cashflows, including fees, plus the marked value of every remaining real-option position. Deposits, withdrawals, paper trades, non-option dust and compute do not become trading profit. Unknown inventory, reconciliation freezes, stale marks or a racing accounting snapshot produce an unknown value instead of a guessed number. The public roster may be clipped; the profit calculation never is.

The project's success measure is **Net = real-options Profit − all input costs**, including model calls, boxes and data subscriptions. Net remains unknown when costs are incomplete. A synthetic test, a holdout pass, a paper route proof and a deposit are not profit.

## Run and verify

Python 3.11 or newer; the pinned Gym dependencies supply numpy, pyarrow and polars. These commands use synthetic inputs and an isolated state directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-gym.txt
.venv/bin/python -m league tick --canary --root /tmp/ltcm-options-canary
.venv/bin/python -m league verify --canary --root /tmp/ltcm-options-canary
.venv/bin/python -m league.ci --no-tests
.venv/bin/python -m unittest discover -s league/tests -t .
npm --prefix gateway run check
npm --prefix gateway test
```

Production runs on Sail through the owner deployment tools. Use a fresh canary directory for each release. A normal `league run` can contact configured services; follow [operations](docs/operations.md) for the production switches, state files and rollback checks. The repository defaults leave real money, automatic updates and the swarm off until configured.

Read-only operator entry points:

```sh
python3 scripts/floor_box.py status --json
python3 scripts/floor_watch.py --json
python3 scripts/gateway_admin.py status
python3 scripts/live_trading.py
```

## Repository

| Path | Purpose |
|---|---|
| `league/house.py`, `service.py` | Responsive supervisor and component composition |
| `league/gym/` | Data reader, deterministic runtime, execution model, statistics and sealed driver |
| `league/swarm/` | Researchers, family store, trials, tournament, gate and forward evidence |
| `league/live/`, `live_trading.py` | Shadow/paper/real routing and the owner's independent grant |
| `league/ledger.py`, `publish.py`, `trading_profit.py` | Audit record and allowlisted public views |
| `league/data_job.py`, `scripts/data/` | Supervised data completion, calibration, images and nightly forward ingestion |
| `gateway/` | External credential, trading and spending boundary |
| `scripts/`, `deploy/` | Owner inspection, pause, deployment, rollback and recovery |
| `archive/docs/` | Historical plans and run records; code history is in git |

[Design](docs/design.md) explains the game and boundaries. [The contract](league/CONTRACT.md) is what a program may read and return. [Operations](docs/operations.md) covers running it. [The changelog](CHANGELOG.md) records deployments; an open draft is not a deployed release.
