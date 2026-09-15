# Portfolio Agent (first generation)

Portfolio Agent ran one persistent S&P 500 paper portfolio on Sail inference, with a Cloudflare
supervisor controlling funding, availability and backups, and published its checkpoints to
[blakewoods.us/portfolio](https://blakewoods.us/portfolio/). Long Term Capital Management replaced
it on September 15, 2026: many desks instead of one portfolio, real venues instead of paper only,
Alpaca instead of Schwab.

These records are historical. The commands, credentials, datasets and code they reference were
removed from the tree with the first generation and remain in Git history. Nothing here describes
the current operating state.

## The project

- [Start here](START-HERE.md) — first-generation entry point.
- [Architecture](ARCHITECTURE.md) — evidence, agent memory, portfolio and publication.
- [Evaluation](EVALUATION.md) — what the Sail experiments measured and what they could not prove.
- [Operations](OPERATIONS.md) — setup, cloud enrollment, execution and recovery.
- [Backups](BACKUPS.md) — private R2 recovery snapshots.
- [Roadmap](ROADMAP.md) and [current state](CURRENT-STATE.md) as of the handover.

## Venues and providers

- [Schwab setup](SCHWAB-SETUP.md) — the read-only brokerage connector, dropped for Alpaca.
- [Sail products](SAIL-PRODUCTS.md), an [earlier measurement pass](SAIL-PRODUCTS-2026-09-12.md)
  and the [source manifest](sail-source-manifest.json).

## Records

- [Run records](runs/) — the September 13 rehearsals, the pre-week impact audit and the
  completed rehearsal.
- [Lessons](lessons/README.md) — optional exercises built from the research bank.
- [Night shift](NIGHT-SHIFT.md) and the [pre-portfolio experiments](pre-portfolio-2026-09-13/README.md),
  which predate the portfolio runtime itself.

[Current project](../../../README.md) · [Docs index](../../README.md)
