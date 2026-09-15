# Sail-native Long Term Capital Management

*Written September 15, 2026, after the owner asked for the floor to leave the MacBook, drop paper
trading, and use Sail's infrastructure to the limit. This is the design being built the same day.*

## The shape

Three planes, each on the infrastructure that suits it, none of them a laptop.

```
                 ┌──────────────── Sail ─────────────────┐        ┌────── Cloudflare ──────┐
  markets ──────▶│ Floor box (Sailbox, always on)         │        │ Order gateway Worker    │
  filings        │  six desks · risk engine · critic      │──────▶│  holds the venue keys   │──▶ Kalshi
  news           │  committee · evolution · publisher     │ orders │  hard caps · kill switch│──▶ Coinbase
                 │  hourly checkpoints = backups + forks   │        │  5-minute watchdog      │──▶ Alpaca
                 │                                         │        ├─────────────────────────┤
                 │ Research fleet (forks of the floor box) │        │ Site Worker + DO        │
                 │  variants, backtests, evolution trials  │──────▶│  event log · checkpoint │──▶ public
                 │ Inference (DeepSeek, Kimi, GLM, oss)    │ events │  WebSocket tape         │
                 └─────────────────────────────────────────┘        └─────────────────────────┘
```

**Floor box.** One size-`s` Sailbox runs the floor loop around the clock. Sail bills observed
use, so an idle-ish 1 vCPU box costs cents per hour. Its disk holds the event log, the model
request ledger, memory and the shadow books. A Sail **checkpoint** every hour is the backup, and
the fork point: a checkpoint can be started as a second box with disk and memory intact.

**Order gateway.** A Cloudflare Worker holds the Kalshi and Coinbase credentials as secrets and
signs every venue request. The floor box never sees a private key. The gateway enforces caps the
desks cannot reach from inside Sail (per-order notional, per-day notional and count) and a kill
switch, and its cron restarts the floor box through the Sailbox API when the public checkpoint
goes stale. Guardrails that matter live outside the machine the agents run on.

**Site.** Unchanged in role: the hash-chained public record and the live tape. It gains an
infrastructure strip so visitors can see the box, its checkpoints and the Sail spend.

## No paper, only shadow

Every desk either trades real money on a live venue or runs as a **shadow**: full sessions, real
research, proposals scored against real prices with the real fee model, no orders sent and no
pretend balance shown as equity. Shadow desks exist to compete for a live sleeve. Meriwether's
gates promote a shadow desk to live capital; retirement sends a live desk back to shadow. Merton,
Rosenfeld, Hawkins and Krasker are shadow until the Alpaca live account is enabled; Mullins and
Hilibrand are live.

## Where Sail is pushed

| Capability | Use on the floor | Status |
|---|---|---|
| Sailboxes | The floor box itself; egress policy limited to the venues, Sail, SEC, market data and the site | building |
| Checkpoints and forks | Hourly checkpoints as backups; forks as research fleets for evolution trials and parallel market pricing | checkpoints today, fleets next |
| Multiple models and completion windows | DeepSeek V4 Pro, Kimi K2.6 and GLM 5.3 desks; Flex for research, ASAP for the critic and live orders; gpt-oss-120b as a cheap screener | live |
| Reasoning output | Full reasoning text published as thoughts | live |
| Usage API | Daily spend on the site; rate-card drift check daily | live |
| Batch API | Nightly post-mortems and evolution rewrites at half price | next |
| Webhooks | Completion webhooks for background Flex requests instead of polling | next |
| Voyages | One trace per session; a dashboard deep link per session if traces prove publicly viewable | next |
| LoRA on Kimi K2.6 | Train the house model on the floor's own scored decisions once there are enough of them | later |

## What the public sees

The home page answers three questions in one screen: how much money, up or down today, and what
it costs to think. Then the six partners, the live tape, and the infrastructure strip. Every
order is published after it fills with the risk decision and the critic's review beside it.
Every evening: six post-mortems and one Meriwether memo. Every settlement: a scored outcome.

## The loop that improves the loop

Every session and every settlement writes to a results ledger folded from the event log: cost,
turns, decisions, hit rate, P&L per inference dollar, drawdown, Brier score for event contracts,
critic block rate, playbook versions. A daily `lab.result` publishes the numbers, and a Markdown
lab report lands in `docs/runs/` so the architecture is judged on evidence, not taste. Evolution
mutates model choice as well as playbooks, cadence and memory, so the floor searches over models
and methods at once; Meriwether's gates move real capital toward what works.

## The only human touch

The gateway's cron reads the Sail balance every five minutes and emails the owner when it is low
and again when it is critical, plus a daily digest and an alert if the box stops, a cap is
exhausted or the kill switch is engaged. After a top-up the same cron resumes the box and
restarts the loop with no human step. Nothing else needs a person.

## Operating rules

- The floor box never sleeps while the loop runs; the gateway watchdog restarts it if the
  public checkpoint goes stale for fifteen minutes.
- Keys live only in Cloudflare secrets and the owner's terminal. The box holds the Sail key by
  credential injection and a gateway token.
- Kill switch in two places: `python3 -m ltcm kill` on the box and `POST /v1/kill` on the
  gateway. Either stops new orders; the gateway's is outside the agents' reach.
- Checkpoints hourly; restore is "start from checkpoint", tested before it is needed.
