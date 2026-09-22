# Model routing, prompt caching and economics — September 22, 2026

Goal document section 3 plus the economics report from section 5. What was built, what was
measured, what the measurements say, and what is still unmeasured. The earlier routing decision
([2026-09-20](2026-09-20-model-routing.md)) stays as history.

## 1. Luna prompt caching

### What was wrong (measured on production, read-only)

15,044 Luna research calls (`provider.request`, profile `openai_luna`, Sept 19–22) sent
367.9M input tokens and read **0** from OpenAI's prompt cache, for $95.45. Every call wrote
almost its whole input to the cache (`cache_write_tokens` 14,467 of 14,470 on a sample row).
On GPT-5.6 and later a cache write bills at 1.25x the input rate and a read at 0.1x
([prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching), read
Sept 22), so the floor paid the write premium on every call and never collected. Sail's own
calls over the same days hit 70% (`pro_asap`) and 79% (`pro_flex`).

The cause was the request layout, not a missing key. `league/fast_research.py` sent the whole
conversation as ONE user message, `{"conversation": [...], "tools": [...]}`. OpenAI's implicit
breakpoint sits at the end of the latest eligible message, and each new turn changed the bytes
before that point (the tool list followed the conversation), so no later request ever matched a
written prefix. The standing (balances, timestamps) also came before the strategy file in the
first user turn, so two passes of one agent could not share the strategy text either.

### What changed

- **Layout v2 (`messages`)**: a developer message every agent shares (protocol, tool schemas,
  rules, contract), then the agent's state, then one message per turn: the model's call as a
  JSON envelope, the House's result as `TOOL RESULT`. Turn N+1 is turn N's messages plus new
  ones, byte for byte (tested). Works through the deployed gateway. **On by default**
  (`league/research_routes.json` `cache.layout`).
- **State order**: `Researcher._state` now puts identity, specialty, strategy file and
  parameters first, then `STATE_MARKER`, then journal, standing and why the House woke the
  agent. Same facts, stable prefix. Sail benefits too.
- **Explicit hints (`explicit_hints`, off until the gateway deploy)**: breakpoints at the end of
  the shared developer message, the agent's static block and the newest turn (at most 4, the
  API's limit), plus `prompt_cache_key: "ltcm-research-v2"` (one task-family key: on GPT-5.6
  the key separates cache accounting rather than routing, so per-agent keys would split the
  shared prefix) and `prompt_cache_options: {mode: explicit, ttl: 30m}`.
- **Gateway** (`gateway/lib/frontier.mjs`): admits `prompt_cache_key` (`[A-Za-z0-9._:-]{1,64}`),
  `prompt_cache_retention` (`in_memory` | `24h`, older models only), `prompt_cache_options`
  (`implicit`/`explicit`, `ttl: 30m`, no prewarm) and `input_text` blocks with
  `prompt_cache_breakpoint: {mode: explicit}` on non-assistant messages; everything else is still
  refused. Settlement now prices a usage block's `cache_write_tokens` at the write rate and the
  remaining uncached tokens at a new optional `uncached` rate (the list price; absent, it is the
  write rate, so old tables bill exactly as before). `wrangler.jsonc` carries the list rates.
- **Metering**: every Luna `provider.request` row now has `cache: {input_tokens, cached_tokens,
  cache_write_tokens, hit_rate, layout, key}` beside the gateway's settled `cost_usd`. A
  turn bought under one layout is rebuilt under the same layout after a release (the call
  table records it), so resumed sessions never trip `research_request_identity_changed`.

### Live evidence through the deployed gateway (implicit mode, no hints), $0.068

Three real conversations; turn A is the conversation one tool round earlier, turn B the full
conversation, sent back to back; effort low, 600 output tokens.

| layout | calls | input tokens | cached (read) | written | billed |
|---|---:|---:|---:|---:|---:|
| v1 packet (production until now) | 6 | 170,839 | 0 (0%) | 170,821 | $0.0461 |
| v2 messages | 6 | 164,916 | 97,222 (59%) | 67,676 | $0.0220 |
| v1, turn B only | 3 | 86,775 | 0 | — | $0.0239 |
| v2, turn B only | 3 | 83,719 | 81,188 (97%) | — | $0.0044 |

A follow-on turn costs 81% less under v2. Two of the three first turns also read 8,017 tokens
from a different agent's request (the shared developer prefix), even without hints. A production
Luna session averages about three calls, so the expected blended hit rate is roughly 70–80% and
Luna research cost roughly 55–65% lower; that is a projection, to be confirmed from the new
`cache` fields after restart.

End to end through the real `Researcher` → `ResearchRouter` → `FastResearch` (v2) → deployed
gateway, on mullins-11's strategy with its recorded market view and a temporary local ledger
(four turns, $0.0051), the `provider.request` rows read:

| turn | tool the model chose | input tokens | cached | written | billed |
|---:|---|---:|---:|---:|---:|
| 0 | `runtime_status` | 10,265 | 0 | 10,262 | $0.002623 |
| 1 | `markets_now` | 10,297 | 10,262 (99.7%) | 32 | $0.000266 |
| 2 | `replay_coverage` | 15,450 | 10,294 (66.6%) | 5,153 | $0.001698 |
| 3 | `library_search` | 15,597 | 15,447 (99.0%) | 147 | $0.000510 |

Blended hit rate 69.8% over the pass; the same four turns under v1 would have written every token
at the write rate (about $0.013). One `route.decision` row recorded the session's route and reason.

**Coordinator step after deploying the gateway** (explicit hints add the cross-agent breakpoint
on every first turn): set `research_routes.json` `cache.explicit_hints` to `true`, release, then
on the box:

```python
import json, sqlite3
db = sqlite3.connect('file:/workspace/state/ledger.sqlite?mode=ro', uri=True)
rows = [json.loads(p) for (p,) in db.execute("select payload from ledger where kind='provider.request' and at > ? order by seq", ('<release time>',))]
c = [r['cache'] for r in rows if r.get('cache')]
print(len(c), sum(x['cached_tokens'] for x in c) / max(1, sum(x['input_tokens'] for x in c)), {x['layout'] for x in c})
```

Expect `messages-explicit` rows and a hit rate above the implicit 59–77%. If the gateway
refuses the hints (HTTP 400 "Prompt-cache hints"), set `explicit_hints` back to `false`.

## 2. Batch inference

Checked Sail's Batch API (`POST /v1/batches`, up to 100,000 `/v1/responses` requests, balanced
or flex windows) and its completion windows. A batch item is priced at its window, the same
price the Provider already buys with background `balanced`/`flex` single requests, so a batch
adds no discount here, only a second polling path. OpenAI's Batch API would need new gateway
routes and a settlement path for bills that arrive hours later. No offline consumer tonight has
the volume to justify either: triage and hypothesis memory run on Jev (TypeSafe), and the
teacher is a handful of Astra calls. **Nothing was built.** The cheap-window path already exists
(`pro_flex`, `pro_balanced`, `flash_balanced`).

## 3. Balanced tier and Flash: the experiment

### Verified model and tier availability

`GET https://api.sailresearch.com/v1/models` (Sept 22) lists DeepSeek-V4-Pro-0813,
DeepSeek-V4-Flash-0731, GLM-5.3, GLM-5.3-Flash, Kimi-K2.6, Kimi-K3, gpt-oss-120b, Gemma-4 31B/12B,
Gemma-4-31B NVFP4 and Qwen3.6-35B-A3B. The rate card shows **DeepSeek-V4-Pro Balanced** at
$0.74 / $0.03 cached / $2.22 and **DeepSeek-V4-Flash Balanced** at $0.07 / $0.02 / $0.14 per
million tokens, neither of which the Provider had. Both are now profiles (`pro_balanced`,
`flash_balanced`); the rate-card drift check covers them.

### Design

Ten real decision points from the production research store, read-only (Sept 21–22): six where
the production model's next action was a `replay` (a strategy file was the useful artifact) and
four where it ended the pass after `markets_now` with a structural blocker (market shut, no
eligible market, record too short), where the correct action is a free abstention (`finish` or
`journal_write`) and a paid action is waste. Every arm answers the same next turn from the same
conversation and tools, twice (r1, r2). Scoring is mechanical:

- a **valid strategy** is a `replay` call whose code passes `check_code`, the sandboxed NEEDS
  probe, `niche_of`, a matching open specialty and `constrain`, and keeps the agent's venue and
  horizon: what `House.spawn` checks before a birth;
- a **correct abstention** is `finish` or `journal_write` on an abstain packet;
- a **well-formed call** is a tool call the House would execute.

Arms: `luna` (production Luna, v1 packet, medium effort, 6,000 tokens), `luna_v2` (the new layout,
same settings; r2 only), `pro_asap` (the production Sail profile, 32,000 tokens, medium,
`tool_choice: required`, `prompt_cache_key league:<family>`), `pro_balanced` (same, balanced
window) and `flash_asap` (DeepSeek-V4-Flash, same settings). Hard cap $4; spent **$0.97** on the
experiment (Sail meter $0.76 plus Luna gateway receipts $0.21) and $0.07 on the live cache check.

### Results

Answers across three repeats (`luna_v2` two). "Cold $/call" prices each arm's provider-reported
tokens at list rates with no cache reads, because identical repeats read each other's caches (up
to 100% on the third repeat) and would flatter later runs; "billed" is what the meters charged.
Useful = a valid strategy on a code packet or a correct abstention on an abstain packet.
Provider errors (HTTP 503 "temporarily unavailable", 25-minute foreground timeouts) count as
failed attempts in the routing rule.

| arm | answered | provider errors | valid strategies (code) | correct abstentions | useful | cold $/call | cold $ per valid strategy | useful per cold $ | billed | median s | p90 s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| luna (v1 packet, production) | 30 | 0 | 13/18 | 11/12 | 24 | $0.0080 | $0.011 | 101 | $0.133 | 7 | 20 |
| luna_v2 (new layout) | 20 | 0 | 8/12 | 5/8 | 13 | $0.0073 | $0.011 | 89 | $0.078 | 5 | 18 |
| pro_asap (production Sail) | 26 | 4 | 2/15 | 11/11 | 13 | $0.0299 | $0.224 | 17 | $0.320 | 32 | 242 |
| pro_balanced | 30 | 0 | 4/18 | 11/12 | 15 | $0.0262 | $0.118 | 19 | $0.384 | 40 | 374 |
| flash_asap | 30 | 0 | 4/18 | 9/12 | 13 | $0.0027 | $0.012 | 160 | $0.052 | 37 | 97 |

Per decision point and repeat:

**r1**

| packet | kind | luna | luna_v2 | pro_asap | pro_balanced | flash_asap |
|---|---|---|---|---|---|---|
| krasker-3 | code | no artifact (finish) | - | valid strategy | valid strategy | valid strategy |
| mullins-11 | code | valid strategy | - | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) |
| haghani-33 | code | valid strategy | - | provider timeout (25 min) | no artifact (journal_write) | valid strategy |
| scholes-23 | code | no well-formed tool call | - | no artifact (journal_write) | no artifact (library_search) | no artifact (markets_now) |
| huang-24 | code | valid strategy | - | no artifact (finish) | no artifact (journal_write) | no artifact (journal_write) |
| meriwether-37 | code | no artifact (library_read) | - | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) |
| mullins-6 | abstain | correct abstention | - | correct abstention | correct abstention | correct abstention |
| hufschmid-29 | abstain | correct abstention | - | correct abstention | correct abstention | free detour (library_search) |
| krasker-2 | abstain | correct abstention | - | correct abstention | correct abstention | correct abstention |
| scholes-22 | abstain | correct abstention | - | correct abstention | correct abstention | correct abstention |

**r2**

| packet | kind | luna | luna_v2 | pro_asap | pro_balanced | flash_asap |
|---|---|---|---|---|---|---|
| krasker-3 | code | valid strategy | valid strategy | provider HTTP 503 | valid strategy | valid strategy |
| mullins-11 | code | valid strategy | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) |
| haghani-33 | code | valid strategy | valid strategy | provider timeout (25 min) | no artifact (journal_write) | no artifact (library_read) |
| scholes-23 | code | no artifact (markets_now) | no artifact (markets_now) | no artifact (replay_coverage) | no artifact (replay_coverage) | no artifact (markets_now) |
| huang-24 | code | valid strategy | valid strategy | no artifact (finish) | no artifact (finish) | no artifact (journal_write) |
| meriwether-37 | code | valid strategy | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) |
| mullins-6 | abstain | correct abstention | correct abstention | correct abstention | correct abstention | correct abstention |
| hufschmid-29 | abstain | correct abstention | free detour (library_search) | correct abstention | free detour (library_search) | correct abstention |
| krasker-2 | abstain | correct abstention | correct abstention | correct abstention | correct abstention | correct abstention |
| scholes-22 | abstain | correct abstention | correct abstention | provider HTTP 503 | correct abstention | free detour (library_search) |

**r3**

| packet | kind | luna | luna_v2 | pro_asap | pro_balanced | flash_asap |
|---|---|---|---|---|---|---|
| krasker-3 | code | valid strategy | valid strategy | valid strategy | valid strategy | no artifact (journal_write) |
| mullins-11 | code | valid strategy | valid strategy | no artifact (journal_write) | no artifact (library_read) | no artifact (library_read) |
| haghani-33 | code | valid strategy | valid strategy | no artifact (library_search) | no artifact (library_search) | invalid strategy (safety check) |
| scholes-23 | code | no artifact (markets_now) | valid strategy | no artifact (replay_coverage) | valid strategy | valid strategy |
| huang-24 | code | valid strategy | valid strategy | no artifact (journal_write) | no artifact (journal_write) | no artifact (journal_write) |
| meriwether-37 | code | valid strategy | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) | no artifact (library_read) |
| mullins-6 | abstain | correct abstention | correct abstention | correct abstention | correct abstention | correct abstention |
| hufschmid-29 | abstain | free detour (library_search) | correct abstention | correct abstention | correct abstention | free detour (library_search) |
| krasker-2 | abstain | correct abstention | free detour (library_search) | correct abstention | correct abstention | correct abstention |
| scholes-22 | abstain | correct abstention | free detour (runtime_status) | correct abstention | correct abstention | correct abstention |


Sail latency is from the Provider's own request rows (created to settled); two r1 rows were
resumed after an interruption and their time includes the gap, which inflates the `pro_*` p90.

### What the evidence says

- **Luna is the strongest economical research route.** 13 of 18 code decision points produced a
  strategy that passes the spawn checks, against 2–4 of 15–18 for every DeepSeek arm, at a
  seventh of pro's cost per call and a fifth of its median latency. A valid strategy cost $0.011
  on Luna against $0.12–0.22 on DeepSeek-V4-Pro. That supports routine research on Luna (the
  owner's 75% cohort) and makes the caching fix the largest single saving available.
- **Pro balanced against pro asap**: 12% cheaper per call cold, as useful (15 of 30 against 13
  of 26 answered), no provider errors against four for asap in this window (two HTTP 503s and
  two 25-minute foreground timeouts on the largest packet), but a slower tail (p90 374 s against
  242 s). The evidence rule picks balanced when switched on; it ships **off** because the
  owner chose asap for speed (`turbo.json`) and the saving is small next to Luna's. Flip
  `routing.sail_by_evidence` if cost matters more than the tail.
- **Flash** costs a ninth of pro per call and about the same as Luna per valid strategy, but
  writes fewer strategies (4 of 18), detours on a quarter of abstain packets and is five times
  slower than Luna. Cheap tokens are not cheap work: it is not a research replacement, and the
  rule refuses it (lower useful rate).
- **The DeepSeek arms mostly read before they write** (`library_read`, `journal_write`,
  `replay_coverage`). A single-turn test scores that as no artifact, so it understates what a
  whole pro session produces; it is still the turn the House pays for.
- **Luna v2 layout** stayed well-formed on every call and wrote strategies at the same cost per
  valid strategy ($0.011), but took a free detour on 3 of 8 abstain packets (a library search or
  runtime status) where v1 did on 1 of 12. That costs a cached turn (about $0.0015), not a paid
  action, and n=8 is small; watch the share of v2 passes that end in `finish` after the restart
  and roll the layout back (`cache.layout: packet`) if abstaining passes grow a turn.
- Sample sizes are small (10 decision points, 2–3 repeats, one turn each). None of this measures
  trading edge; it measures whether a model produces an artifact the House can evaluate.

## 4. Task-aware routing (`league/routing.py`)

A table from task to route: deterministic work (market availability, data freshness, fills and
refusals, budgets and admission) to code; cheap semantic decisions (research gate, triage,
hypothesis rewording) to Jev; routine research to the strongest economical option by measured
evidence; strategy synthesis, repair patches, audits and consultations to Astra. It is wired
where the researcher chooses its provider: `ResearchRouter.settings_for` asks the `TaskRouter`
for every new session, which records the route, model and reason as `route.decision`, aggregated
into one row per hour, task, route, model and reason with a count. With `sail_by_evidence` on,
a Sail session moves to a challenger only when its useful-artifact rate (not raw count) is at
least the baseline's, with at least 10 samples, and its useful artifacts are cheaper per dollar
(`league/routing_evidence.json`, from this experiment). Switch: `research_routes.json`
`routing.record` (on) and `routing.sail_by_evidence` (off). Provider errors count as failed
attempts in the rule, so a flaky route cannot win on the answers it did return. Earned
consultations (`consult` → Astra) and agents' `classify` calls (`agent_classify` → Jev) are
recorded the same way.

## 5. Traces for eventual fine-tuning (`league/traces.py`)

Every finished research pass writes its transcript (inputs: the first two messages, tools and
settings; outputs: every later turn; the kept candidate) to a private gzip file under
`<House root>/traces/` (0700 directory, 0600 files) and a `trace.record` pointer on the ledger:
`{task, id, version, model, inputs_sha256, outcome, cost_usd, useful}`. Outcomes:
`candidate_passed`, `candidate_failed`, `abstained` (useful unknown) or `ended: <reason>`. A
later outcome is a new version of the same id, append-only (`TraceStore.outcome`):
`House.research` joins what it did with the candidate (`adopted`, `forked`, `fork_deferred`,
`not_adopted`; useful only when installed AND replay-passing), and a verified repair can be
joined the same way. A capture failure raises an `ops.alert`, never a failed pass. Switch:
`config.json` `research_traces` (default on). Collection only; no training.

## 6. Economics (`scripts/economics.py`)

Read-only (`mode=ro` plus `query_only`), standard library only, runs on the box through `rx.py`. Production at 13:28Z, Sept 22:

```
1. TRADING P&L AFTER EXECUTION COSTS (real and practice are never summed)
   REAL MONEY     closed  W/L   gross   fees    net    House  MTM chg  staked
   alpaca              0  0/0   +0.00   0.00   +0.00  +0.0000   +0.00    0.00
   kalshi             10  7/3   -3.31   1.09   -4.40  -0.0035   -3.90   65.29
   PRACTICE MONEY (paper / shadow)
   alpaca-paper       56 43/13 +14.23  10.47   +3.76  +1.2022  -10.52  2,599.81
   kalshi-shadow     286 239/47 -208.55 7.51 -216.06  +0.0000 -270.97  4,974.75
   REAL ACCOUNT RETURN, the public site's definition (league/publish.py)
     start_equity 1,017.3551 at 2026-09-19T04:56:53Z; account_equity 1,013.4533
     tracked profit (site pnl_total) -3.9018 = -0.3835% of start; recomputed from book rows: -3.9018
     tracked profit less ALL recorded model/infra spend in the window: -261.14
2. MODEL AND INFRASTRUCTURE SPEND BY PROVIDER (Sept 19 21:13Z .. Sept 22 13:28Z, 64.3 h)
   openai-luna  $95.6728  15,075 research requests, gateway-verified
   openai-astra $82.3253  Merton architect 25.54, toolsmith 13.75, operator 12.15, teacher 11.47,
                          consultant 10.97, designer 5.88; audits 1.61; semantic rubrics 0.86; grants 0.08
   sail         $64.9900  balance meter (research tokens pro_asap 30.78, pro_flex 10.92, unrecorded 15.43,
                          sandbox 2.30; House box and unattributed 5.56)
   jev          $14.0258  semantic lab 14.02, classify 0.005
   web-search   $0.2200   flat internal charge (estimate)
   TOTAL        $257.2339
3. USEFUL WORK PER DOLLAR (denominator: research model spend $163.86)
   replay-passing candidates: 78 unique -> 0.476 per $, $2.10 each (405 failing)
   adoptions of replay-passing code: 68 (13 in place on rung 0, 44 rung-1 rewrites, 11 forked children) -> 0.415 per $
   verified repairs: none yet (no repair.status rows)
4. WARNINGS: real alpaca 0 and real kalshi 10 closed trades (< 30); $65.29 staked on real Kalshi;
   2 Luna requests with unknown bills; never sum practice and real money, never compare unequal
   stakes, never rank samples this small.
```

Definitions and caveats the script prints in full: `docs/account-performance.md` still describes
the Sept 16 basis; the code's basis since Sept 19 (`league/publish.py`, `league/config.json`) is
what the site publishes and what the report recomputes to the cent. Net external flows are read
live from the venues and are not in the ledger, so the raw-balance version is reported as not a
return. The site's `sail_model_spend_total_usd` ($152.80) counts every research-token charge,
including the $95.67 OpenAI Luna served. Astra and Luna figures are gateway cost headers, not
invoices. Run it with
`python ~/Work/ltcm-watch-2026-09-21-eight-hour/rx.py scripts/economics.py --ledger /workspace/state/ledger.sqlite`
(add `--json` for machine-readable output, `--since`/`--until` for a window).

## 7. Tick latency diagnosis (analysis only)

Ticks: Sept 20–21 p50 60 s / p90 60 s (5.7% overran); Sept 22 p75 83 s, p90 139 s, max 274 s.

- **Main cause (measured): a lock convoy in the research queue.** Each new session's research
  thread takes `_lifecycle_lock` in `House.research` and computes `_research_standing` →
  `research_capabilities` → `semantic_lab.evidence` → `stats()`, two full scans of a 137k-row
  table (about 1.4 s on an idle box). The tick's next `queue_research` waits: p50 1.92 s, p90
  4.18 s after a new session (n=4,744) against 0.05 s after a resumed one. Ticks queue p50 5,
  p90 33, max 62 new sessions. The research-queue phase was the largest in 101 of 152 overrun ticks.
- Other phases (measured): venue poll and settle p50 7.2 s; wakes p50 10.7 s; the tail
  (payout, horizon, tuition, population, save, publish, health) p50 27.7 s, 30.1 s with a birth
  or death; publish plus health p50 7.8 s. Stack dumps of ticks over 180 s: 5 in Sailbox
  sleep/resume (4 in `_refill` → `spawn` → `sandbox.needs`, 1 in `_admit_candidate` → `fork` under
  the lock), 3 waiting on the lock in `_enforce_tuition`, 1 ledger scan, 1 publisher checkpoint,
  1 research queue.
- **Applied (the one trivial fix):** `SemanticLab.stats()` takes a `max_age`, default 0 so every
  other caller is unchanged, and `evidence()` (the call inside the research lock) reuses a copy up
  to 60 s old; the cooldown is never stale. Expected to cut about 1.4 of the 1.9 s each new session
  holds the lock (estimate from idle timings; the House is paused, so unmeasured under load).
  `House._health` still takes a fresh count each tick (about 1.4 s); passing `max_age=60` there is
  a one-line follow-up left out to avoid colliding with the Jev branch's edit on the next line.
- Safe next: compute `research_capabilities` before taking the lock; checkpoint the publisher
  every 300 s instead of every tick; cap new research sessions per tick (a policy call).
- Risky: moving births or `_admit_candidate`'s Sailbox work off the lock, taking submit, cancel
  or wind-down off the lock (money path), caching `evaluator.rung` per tick.

## Switches and rollback

| switch | where | default | rollback |
|---|---|---|---|
| Luna request layout | `research_routes.json` `cache.layout` | `messages` | `packet` |
| Luna cache hints | `research_routes.json` `cache.explicit_hints` | `false` (needs gateway deploy) | `false` |
| Route records | `research_routes.json` `routing.record` | `true` | `false` |
| Evidence-moved Sail profile | `research_routes.json` `routing.sail_by_evidence` | `false` | `false` |
| Research traces | `league/config.json` `research_traces` | `true` (absent) | `false` |
| Gateway cache hints and write pricing | gateway deploy | needs deploy | redeploy previous gateway |

## Unfinished

- Explicit cache hints are unverified live until the gateway is deployed (step above).
- The Astra role and audit call sites, the Jev floor and the repair worker do not yet ask the
  `TaskRouter` for their route; research sessions, earned consultations and agent `classify`
  calls do. The table documents the rest and `TaskRouter.route()` is ready for those owners.
- Trace outcomes are joined when the research pass commits (adopted in place, forked, fork
  deferred, not adopted); a fork admitted on a later tick is not re-joined yet. Repair traces
  need the repair worker to call `TraceStore.capture('repair', ...)`.
- The lock-convoy fix is applied only to `evidence()`; the other safe fixes above are described.
- The Luna v2 abstention detour (3 of 8) needs production confirmation.
