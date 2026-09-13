# Architecture

One persistent coordinator maintains the portfolio and research state. Research branches can investigate alternatives; only the coordinator can admit a paper allocation. The public site reads a small saved projection.

| Component | Responsibility |
|---|---|
| [`evidence.py`](../portfolio_runtime/evidence.py) | Capture dated constituents and SEC financial facts, preserving sources, periods and hashes. |
| [`runner.py`](../portfolio_runtime/runner.py) | Pace research waves to a wall-clock deadline, recover requests and publish checkpoints. |
| [`research.py`](../portfolio_runtime/research.py) | Choose unresolved questions, retain prior work and compare research methods. |
| [`provider.py`](../portfolio_runtime/provider.py) | Freeze Sail requests, reserve cost and recover accepted responses by identity. |
| [`ledger.py`](../portfolio_runtime/ledger.py) | Record paper decisions, fills, cash, holdings and sourced valuations. |
| [`sail_host.py`](../portfolio_runtime/sail_host.py) | Provision restricted Sailboxes, preserve state through restart and isolate research forks. |
| Public checkpoint | Publish portfolio state and template-based progress without raw model responses or credentials. |

## Evidence and decisions

The initial universe contains 503 listed securities, captured on September 13, 2026. Membership comes from a [community-maintained list](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies); financial observations come from the [SEC Companyfacts API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). All 503 captures succeeded.

These are selected whole-company US-GAAP facts, not complete filings or a licensed constituent feed. Delayed Yahoo Finance observations from September 11 accompany the research bank; they are valuation inputs, not executable quotes. Custom tags, segments and industry-specific measures may be missing. Annual, quarterly, year-to-date and balance-sheet observations retain their original periods. A filing captured later cannot silently enter an earlier evidence cutoff.

The first sustained run starts with this frozen bank. Later waves address coverage gaps and questions raised by previous work, with bounded retrieval of pre-cutoff annual filings for deeper evidence. Every new capture retains its original source and hash. Memory carries earlier analyses and failures; numerical claims are checked against the original observations. Passing that check does not establish a sound valuation or justify a trade.

Proposals specify a complete target portfolio, leaving any unallocated weight in cash. The current mandate is long-only, no leverage, at most 20% per stock, with $100,000 of **virtual** starting capital. Deterministic ledger checks apply independently of model confidence.

## Paper execution and performance

A proposal is not a fill. Paper execution requires a still-valid constituent snapshot, a sourced market session and prices available after the decision. Quote execution buys at the ask and sells at the bid. The separate daily-bar path uses a later session's opening price with fixed modeled slippage; it is not an intraday fill simulation.

The ledger records fees, external funding and exact decimal amounts. Time-weighted returns exclude external deposits from investment gains. Benchmark comparisons require matching S&P 500 total-return observations. The paper adapter validates Yahoo Finance’s specific `^SP500TR` index feed, keeps its source hash and synchronizes opening and closing observations with portfolio valuations; it does not claim licensed exchange data. Missing benchmark data stays missing; an ETF or a price-only index is not substituted. Research expenses are tracked outside portfolio returns.

Unresolved corporate actions can suspend execution and invalidate current marks. Sunday research may produce a pending allocation, but cannot produce a Sunday regular-session fill. Historical or synthetic prices are never presented as a live track record.

## Persistence and publication

Separate SQLite journals hold requests, research and paper events. Request bodies, model profiles and reservation identities are immutable. Recovery retrieves an accepted response; uncertain usage retains its reservation. A completed provider response can still fail source checks.

The Sailbox adapter installs a frozen bundle and starts a managed process with a deadline. A separate watchdog on the owner's computer checks progress and restarts that process on the same cloud disk if needed. The cloud image has no verified native boot service: recovery and timely resource cleanup depend on the watchdog remaining available. A live readiness test verified credential injection, restricted routes, sleep/wake, process restart and restoration of a compressed SQLite backup.

Research forks start from a sterile checkpoint, receive separate assignments and reserved allowances, and have no publication authority. The first fork experiment compares full-universe context with a smaller context selected for five identical company questions. The coordinator's restricted egress policy permits its provider, public-source and publication routes. Credentials are injected into permitted requests outside the guest environment.

The website accepts only a validated checkpoint. Public reads cannot start inference or submit paper orders. It shows the last publication time, pending allocations separately from holdings, and returns only after sourced observations exist. The Schwab connection is paused; there is no live execution service.

[Experiment design](EVALUATION.md) · [Operations](OPERATIONS.md)
