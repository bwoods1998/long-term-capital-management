# Inference Economics Lab

A small, reproducible lab for learning how AI inference and agent workloads connect to financial decisions.

Current status: private credential setup and read-only Sail preflight. The extraction experiment and spending controls are next; no paid inference has been submitted by this project.

## Setup

Use Python 3.10 or newer. These setup scripts use only the standard library.

```sh
python3 scripts/setup_key.py
python3 scripts/check_connection.py
```

The first command accepts a hidden key in your terminal and writes an owner-readable `.env` excluded from Git. It refuses to overwrite an existing file. Never paste keys into chat or commit them. Your dashboard key name can be anything; the local variable is `SAIL_API_KEY`.

The second command performs GET requests for the model catalog and credit summary. It prints only availability and balance, never the key or raw responses. Catalog inclusion does not guarantee immediate serving capacity.

## First experiment

One public filing excerpt, a handful of manually verified financial facts, and one bounded model call. Then expand to a small held-out evaluation set. Measure correctness, completion time, tokens, cached tokens, and cost per successful extraction.

Start with DeepSeek V4 Flash 0731 through Sail. Confirm current prices and availability before running. Initial target: at most $1 of the $5 trial credit, with conservative pre-submission reservations in the future runner. No cloud VM or GPU rental is needed.

See [API review and implementation notes](docs/SAIL-API-NOTES.md). The [source manifest](docs/sail-source-manifest.json) records the documentation snapshot; original vendor docs stay in ignored `.data/`.
