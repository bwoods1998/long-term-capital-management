# The desk's daily pages

The House writes these pages itself, from the V3-A part 1 deploy on: one page a UTC day, `<YYYY-MM-DD>.md`, written by
its `scoreboard` job at 23:30Z (`league/ops/scoreboard.py`) and committed to `main` through the gateway's docs route
(`POST /v1/github/docs`). Their commits start with `desk:`. Nobody edits them by hand: a correction goes in the run
record ([the unattended desk](../2026-10-02-unattended-desk.md)). That release is built and not yet deployed, so until
its deploy this folder holds only this page.

**What a page says**, from the House's own records only:
- the running release; self-deployed releases and self-rollbacks (today and since the reset), owner deploys and
  rollback drills;
- realized options P&L since the Sept 26, 2026 reset and over the trailing 30 days, input costs by service since the
  reset, and **Net** (realized minus costs; deposits are never profit), all at the latest close economics' cutoff;
- how many lots are open and what they are worth at conservative marks;
- the research budget's state (for example "research at floor") and, per meter, its research dollars a day and the next
  date a card is needed;
- the forward ladder's counts: entrants, promoted and the false-discovery family's size ("n/a" while the ladder is not
  deployed), and how many cohorts are in practice;
- how many of the House's jobs ran, failed, were missed or skipped that day.

**What a page never says.** It is built from an allowlist of figures and is refused before posting if it names account
equity, a balance, buying power, a quote, a strike, a contract symbol, a parameter, program text, a Sail box id or a
Validation or holdout figure. Licensed market data never reaches it.

**When there is no page.** The gateway takes at most six desk commits a New York day and only dated names under this
folder, so this README is never written over. A page that fails the filter, or a day the docs route cannot be reached,
leaves the page on the House only, and the job's receipt says why. Until the House's own close economics has run at a
close, a page says it has none.
