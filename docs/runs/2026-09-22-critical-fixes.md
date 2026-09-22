# Critical fixes — September 22, 2026

The owner asked for everything critically important to be fixed. A read of the whole league
(code, live ledger, gateway) at 03:55 UTC found two budget lines that would stop the floor
within hours, frontier consultations that were paid for and came back empty, House secrets
within reach of Merton-written code, and a gateway cap that under-counted one kind of real-money
order. Each fix below is tested; none changes a money rule, so the live grant
`earned-live-20260921` is untouched.

| Problem | Evidence | Fix |
|---|---|---|
| The Sail meter's monthly line would stop the whole floor with the owner's new credit unspent | `budget.py` stops research, Merton, payouts and births at `budgets.sail_month_usd` ($100) of September Sail spend. It read $55.97 at 03:45 and climbed $2–2.80 an hour under the turbo layer: about 16–22 hours to a stop. The owner's $100 Sail top-up of Sept 21 (`topup-20260921-2210:sail`) raised the campaign ceiling, not this line: one owner decision held in two places | `CampaignBudget.topped_up(kind, month)`; the meter's line is the constitution's plus the owner's recorded top-ups that month (`Budget.line`). September's line is $200; October's starts at $100 again. The constitution is unchanged |
| The audit reserve read the wrong meter | The tiers that keep the last OpenAI dollars for audits read only the gateway's month ($166 left). The House's own campaign books every call at its ceiling prices, about twice the gateway's, and had $139.12 left at 03:22 while committing about $17 an hour; it refuses every call at its line, audits included, while the tier said "all" | `House.frontier_remaining()`: the tier reads the tighter of the two lines (the campaign's value is cached 30 s). The alert now says "frontier budget" |
| Consultations were paid for and came back empty | At 12,000 output tokens and "high" effort, 5 of 7 consultations after midnight spent the whole allowance reasoning and were refused as incomplete; the agent paid about $0.73 each (huang-6: $2.24 for three blank answers). The ones that finished cost the same, so they were at the ceiling too. The auditor answers at "medium" in 12,000 and has never run out | 16,000 tokens (the gateway's ceiling) at "medium" by default; `consult.max_output_tokens` and `consult.effort` in the game file override, clamped to 4,000–16,000 |
| Merton was told he saw evidence he never received | The consultation brief says he is shown the agent's own recent trades and where its replays won and lost. The packet held neither: no trades, and a replay `digest` field that `eval.trial` rows never store | The packet carries the agent's last 40 fills and settlements (dust excluded) and the replay digests of its last four retained candidates; each retained candidate now keeps the digest its replay returned (private, never published) |
| Merton-written code ran beside the House's secrets | The updater's vet runs `league.ci --content-only`, which executes strategy code Merton wrote, in a subprocess that inherited the House's environment: the gateway, Sail and site tokens (`service.load_env`). Only the source scanner stood between them | The vet subprocess gets a scrubbed environment (`updater.vet_environment`: PATH, HOME, locale, TZ, TMPDIR only; not `LEAGUE_ENV`) |
| The gateway's independent order cap under-counted Kalshi NO buys | A v2 order's `price` is on the YES scale for both legs. Buying NO at $0.96 goes out as `side: "ask", price: "0.0400"` and was metered at $0.04 a contract: the $75 cap admitted up to 24 times its real principal. The House's own book priced it right; the gateway is the boundary that must hold if the House does not | `kalshiNotional` takes the price on the leg the order trades: the complement for an entry on the ask and for an exit on the bid |

## Not fixed here, recorded for the next pass

- **The House tick is overloaded.** On one vCPU at load ~2, ticks took a median 60 s, p90 151 s and
  up to 224 s (Sept 22, 03:06–04:23). The tick waits on the lifecycle lock held by background
  research, replay and fork jobs, and does network work inline (forking newcomers, audits). The
  watchdog rolls a release back when `health.json` is 300 s old, so a slow tick during a deploy
  watch can roll back a good release. Moving audits and forks off the tick, or a larger box, is
  the fix; neither is a small change on a real-money system.
- **Audits block the tick** for as long as the frontier call takes (up to 570 s at the gateway).
- **Architect pull requests collide** on `league/strategies/registry.json`: each rewrites the whole
  file from the running release's copy, which lags `main`. After #71 merged, #72 and #73 dropped
  its row and failed CI; both are still open.
- **`Merton.follow()` stops polling** a pull request once CI refuses it, so a later repair and
  merge never reaches the ledger (#46).
- **The designer's bounds** cover 8 economy and 3 horizon keys, and live in the file the designer
  edits; `merton`, `frontier_reserve`, `consult` and `audit` are unbounded. It has never tried.
