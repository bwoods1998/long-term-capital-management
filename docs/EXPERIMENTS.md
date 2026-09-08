# First extraction experiment

A small lab for learning how AI workloads connect to financial decisions. V1 measures one financial extraction through Sail: correctness, time, tokens, and estimated cost. Python standard library only; no cloud VM required.

## Start here

Read [Lesson 1](../lessons/01-first-experiment.md), then inspect the request without spending anything:

```sh
python3 lab.py preview
```

Set up a private key and verify access if you have not already:

```sh
python3 scripts/setup_key.py
python3 scripts/check_connection.py
```

The setup command hides input and writes an owner-readable `.env` excluded from Git. The connection check performs only read-only requests. Neither prints the key.

Run one paid trial with your own prediction:

```sh
python3 lab.py run --prediction 'I expect all five facts correct for less than one cent.'
```

The program prints a run ID and saves its request, source, reference answers, response, and usage in `.data/runs.sqlite`. If the job is still pending or submission was interrupted, use the same ID:

```sh
python3 lab.py resume RUN_ID
python3 lab.py report RUN_ID
```

Resume retrieves accepted work; an uncertain submission reuses its original idempotency key within 23 hours. After that it refuses to resubmit and requires manual reconciliation. An incomplete response is terminal and still may incur charges. No automatic new trials or cloud resources are created.

## Budget and measurement

Each intended trial permanently holds a one-cent allowance in SQLite against a $1 local budget. Reservations are atomic and survive failures/restarts. They are deliberately not released after cheap successes, keeping this first version conservative. Keep the database: deleting it also deletes the budget history.

The allowance is a local spending control, not a provider-enforced account cap. It covers this fixed small prompt, model, output cap, and the September 7, 2026 price snapshot with a wide margin. Recheck prices before future experiments; provider price changes, other applications, or separate databases are outside this control. The runner also checks reported credit before a new trial, but billing data can lag.

Actual usage is priced separately using uncached input, cached input, and output. Cost is an estimate, not a reconciled invoice. Missing usage stays unknown. One-cent allowances are not actual spending. The first experiment measures client-observed wall time, including polling and any resume delay, not GPU time.

## What counts as correct?

All five facts must have the right value, USD currency, millions unit, fiscal period, and exact source row. Source data and reference answers are in [the fixture](../data/msft-2025.json), transcribed from [Microsoft's annual report](https://www.microsoft.com/investor/reports/ar25/). The answer key is not part of the model prompt. A completed response with all checks passed is a successful task.

One easy development example cannot establish model quality. Next: controlled synthetic changes, then a held-out dataset, then repeat trials and model/window comparisons. Financial extraction is our initial workload for learning infrastructure economics.

## Verification and references

```sh
python3 -m unittest discover -s tests -v
```

Tests cover incorrect years/units/evidence, cache accounting, concurrent budget limits, uncertain submissions, and terminal-response handling.

[API notes](SAIL-API-NOTES.md) explain the implementation choices. The [source manifest](sail-source-manifest.json) identifies the archived vendor documentation. Keys, runs, reports, and vendor snapshots remain ignored by Git.
