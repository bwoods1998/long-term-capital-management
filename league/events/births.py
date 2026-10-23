"""R3: BIRTHS, THE SWARM'S GENERATOR (goal-2026-10-19/R3-SPEC.md; the owner's goal V2 item 2: "Births come from your
architect agents and from you, using outcome-free facts, rationed by an expected-false-pass budget you state").

PREREG-EVL-1/2/3 are hand births (the captain's). R3 makes births continuous and cheap, with the judges untouched: a
birth is DATA, never code. It plugs into the lane through one loader (league/events/programs.py `load_births`, behind
league/ci.py's wall): each registered birth becomes a Program row with its own registration time, PREREG-EVL-3's
learning band, screen and minimums, AFTER every PREREG program, so the lane decides it, the screen judges it
(PREREG-EVL-3's looks: events counted, alpha 0.018, >= 40 issuers and >= 8 session blocks), the bands move it and the
House's event book trades it at learning size like any version 2 program. No PREREG program's selection, judge or
constant moves (league/tests/test_events_births.py holds every PREREG program's intents identical with and without
births).

THE GRAMMAR (R3-SPEC section 1, its fields and only those; `parse` refuses anything else, so a birth is never free
code). A spec is a JSON object of exactly `FIELDS`:
- `id`: "EVL-B-..." (upper-case letters, digits and dashes; never one registered, never ending "-CTRL"). A NAME IS
  NOT PART OF THE RULE (A95, the captain's, 02:25Z Oct 22, 2026: the first births night's six specs were all refused
  for ids like "EVL-ERN-NEGATIVE-O1"): an id that lacks the "EVL-B-" prefix is named canonically by the House
  (`canonical_name`: a leading "EVL-" becomes "EVL-B-", any other id takes "EVL-B-" in front), and every check of an
  id applies to that name; the canonical line and the sha carry the name, and the candidate row keeps the proposed id
  beside it (`figures.named`);
- `version`: 1 (births are seatable at version 1; a change is a new birth);
- `family`: an event family the lane already reads (`FAMILIES`): ern (8-K item 2.02, open), ern-react (8-K 2.02 in the
  close window, with its reaction), 8k (8-Ks with an ITEM SET, never 2.02), ins (Form 4 cluster triggers), ins-buy
  (director or officer open-market buys >= $50,000, with value and ROLE filters), news (overnight single-symbol
  articles), news-day (the day's articles to T29), news-react (the day's articles with their reaction);
- `rule`: the selection rule, only the family's fields (`RULE_FIELDS`): `items` (the 8k family's item set: an 8-K
  qualifies when it carries one of them); `score_min` / `score_max` (thresholds on the STORED PROMPT-DOC or PROMPT-NEWS
  score, -3..3) and `guidance` (the stored PROMPT-DOC guidance, the ern and 8k families): never a new prompt;
  `react_min` / `react_max` (the reaction ratio, PREREG-EVL-1's C1 measure: the 15:29 minute's close over the last
  close before the event); `value_min` (dollars, >= the lane's own $50,000) and `roles` ("director" | "officer"; a
  one-role list such as ["officer"] reads as its role, A95, and any other list is refused) for Form 4; `sources` and
  `hours` (the news windows: the article's source, and its knowable hour in New York);
- `entry`: the family's own ("open" for ern, 8k, ins, ins-buy, news; "close" for ern-react, news-day, news-react);
- `exit`: "close" (the close of session h) or "open" (a close entry's next open, PREREG-EVL-2's overnight rows); an
  open entry exits at a close;
- `hold`: h in 1..5 sessions; a SEATABLE birth holds one (the screen's blocks are one-session blocks, as every seatable
  PREREG program's; a longer hold is a record, as PREREG-EVL-1's ERN-READ-O3);
- `rank`: the ranking key when room is short: "score", "reaction", "value" or "none" (the family's own, `RANKS`);
- `seatable`: true (real money at learning size from its first event, judged by PREREG-EVL-3's screen) or false (a
  record: free, never seated, never screened); an `ins` (Form 4 cluster) birth is false only (A89: real money cannot
  read a cluster as stored before its decision).
A READ birth (a verdict threshold, a guidance filter or a score ranking) carries its CONTROL, derived from its spec
and registered with it (`control_spec`: the same rule with every verdict condition removed, a record with the id
"<id>-CTRL"): PREREG-EVL-1 section 7's "for a READ program, its mean block value exceeds its control's" holds for a
birth too (league/events/screen.py `control_of`). The canonical form (`canonical`) is the parsed spec as JSON with
sorted keys and no spaces; its sha256 (`sha`) names the birth.

THE FACTS (`Facts`): what the ARCHITECT reads, OUTCOME-FREE. Over the last `SESSIONS` (20) sessions: event counts by
family, 8-K item, form, news source and knowable hour; the stored verdict scores and guidance; which families and items
no program selects; every registered program's selection count (PREREG-EVL-4's and -5's too from release 1019h, below);
and a candidate rule's selection count (each run through the lane's own `select` over the same windows). The facts NEVER
read bars, marks, outcomes, looks, bands, band_history, real_fills, the universe (its prices) or meta (the looks'
details): a SQLite authorizer refuses those tables for the whole build (`outcome_free`), so a price after an event, a
return, a P&L, a look's p or a band cannot reach the architect. Eligibility is the lane's kept result (`eligibility`:
listed, operating, priced before the session), the session's own or else the issuer's nearest. The reactions of the
react families are prices after the event: never read, so their counts are UPPER BOUNDS (every event passes the
reaction) and say so.
PREREG-EVL-4'S AND PREREG-EVL-5'S FAMILIES (release 1019h; PREREG-EVL-5 section 7, "births.py's facts for the new
families"; the review of release 1019g found every one of their nine rows selecting 0, so no Jaccard was computed
against them): their rows are read as their close decision reads them (league/events/programs.py `close_rows_4`,
`close_rows_5`, `FILE_FAMILIES` here), with every price unread, so a count that reads one is an UPPER BOUND as a react
family's: EVL-8K-REACT-ON's reaction passes as any react family's; PREREG-EVL-5's reaction passes each row's own band
(`UNREAD_IN_BAND`: <= 0.96 for EVL-ERN-DROP-ON, inside 0.96-1.04 for EVL-ERN-UNDER-ON and its control) and its gap
passes (EVL-NEWS-NIGHT2-ON); its skips that read a price (TAKEN AT D'S CLOSE BY AN EARLIER ROW (a) and (c), the <= 0.96
skip) skip nothing, while (b) (a stored PROMPT-NEWS verdict `ok` with score >= 2) skips as in the lane, and an issuer
waiting on an unanswered article is counted; NO NEW INFORMATION (i) names an issuer by the kept eligibility's ticker of
it (SEC's tickers copy is read through `meta`, which the facts never read), naming no more than the lane's copy does,
and (ii) and (iii) read the 8-Ks and Form 4 buys as the lane does. Every one of those readings can only add events, so
the facts' count of such a row is at least what the row selected on the same eligibility; the rows that read no price
(EVL-8K-READ-ON, EVL-NEWSPM-READ-ON and their controls) are counted as their decision reads them, on the kept
eligibility (registration set aside, as every count here).

THE VALIDATOR (`validate`, code, not a model): the grammar; a new id and sha; a minimum rate: a SEATABLE birth >=
`MIN_RATE` (20; SUP-3's rate rule, the captain's A97, release 1019h) selected events a session over the sessions of
the last 20 that hold a COMPLETE RECORD PASS (`recorded_sessions`: an outage session is left out, at least
`MIN_RECORDED`, 3, of them), so that it can fill a Probe row's slots after the real-money funnel through the season (a
react family's count is an upper bound, so the floor barely binds it); a RECORD >= `RECORD_MIN_RATE` (3) a session over
the calendar's last 20 sessions by selection count, as before; no duplicate, the Jaccard of the last 20
sessions' selected events < `JACCARD_MAX` (0.8) against every registered program (records, controls and births too:
stricter than "every live program", and it reads no band) and every birth accepted before it the same night; and THE
FALSE-PASS BUDGET (R3-SPEC section 3 as the captain's A81 states it, 16:25Z Oct 21, 2026): each seatable birth adds
0.10 expected false passes (the measured zero-edge pass rate of PREREG-EVL-3's screen is at most 8.4%; 0.10 is the
stated charge, the screen's `FALSE_PASS_RATE`), at most A71's stated lifetime budget of the lane, 3.0
(league/events/screen.py `LANE_BUDGET`, PREREG-EVL-4 section 3), over every seatable version ever registered in the
lane, counted from SEATING's own sum as the report counts it (league/events/screen.py `expected_false_passes`:
PREREG-EVL-1 to -5's fifteen seatable versions, 1.5 (PREREG-EVL-4's three and PREREG-EVL-5's three included,
release 1019g), and 0.10 for every seatable birth once loaded; never a figure written here), and at most
`SEATABLE_A_NIGHT` (3) seatable births a night: so at most fifteen seatable births before the budget is spent. A
retired program's past looks stay counted (a test that was run is never refunded). Records are free.

THE PROPOSER (`propose`): ONE gateway call a night to claude-opus-5-5 (`MODEL`: Claude Opus 5.5 from release 1019h,
the captain's A109; claude-haiku-4-5-20251001 to release 1019g, whose proposals were narrow rules and duplicates; the
verdict reader, league/events/verdicts.py `MODEL`, stays Haiku 4.5) with NO SAMPLING PARAMETER and effort "low"
(`request_body`: Opus 5.5 answers a temperature with a 400 and always thinks, its thinking counted in `MAX_TOKENS`
6000; release 1019g's Haiku call was at temperature 0 with 3000) through the lane's `/v1/claude/messages`, as the
verdicts, STREAMED (release 1019h's fix round, `STREAM`: an unstreamed thinking answer outlasts the lane client's
45-second read; the socket waits `STREAM_GAP` for a byte, the answer at most `CALL_LIMIT`, and on the House the call
starts only with both left before the job's bound), its prompt's sha256 recorded and its answer stored like a verdict
(`birth_calls`, keyed by night, prompt sha and model: a night's stored answer is read again, never asked again, while
the prompt is the same; a new prompt sha is a new prompt, whose answer a night has not been given). A CALL THAT WENT OUT
IS NEVER ASKED AGAIN THAT NIGHT (`LOST`): one lost on the way (a stream that broke, went quiet or ran past its limit, no
answer while waiting, a 5xx the gateway did not settle) is stored `lost` at the gateway's stated cost when it read the
usage, else at its worst case, so it counts in the night's cap, the lane's line and the site's bill; a night whose call
ended without an answer finishes its receipt `unanswered` and the House warns. At most `K` specs
a night, under a cost cap
of `NIGHT_USD` ($0.25) a night: the call's worst case (its input at about 3 characters a token and its max_tokens, at
THE MODEL'S OWN PRICES, `PRICES`: Opus 5.5's $4 and $20 a million tokens in the gateway's CLAUDE_MODELS row, at that
row's dearest inference geography, US-only at 1.1x, so $4.40 and $22, never under what the gateway can settle: $0.132
for the 6,000 tokens out, thinking included, and about $1.47 a million characters in, so the night's whole $0.25 holds
a prompt of about 80,000 characters) must fit under what the night has left, or no call is made. On the House the
call is INSIDE THE LANE'S LINE (release 1019e's review): its worst case must also fit under what is left of the lane's
line today (league/events/house.py `line_left`), and its stored cost counts in that line, in the budget rule's measure
of the lane (league/ops/budget.py `lane_spend`) and in the site's bill (league/site_lane.py `verdict_usd`).

The prompt (`USER`, A95) shows two VALID specs (`EXAMPLES`: an 8k spec over items outside `READ_ITEMS_8K` with no
score or guidance field, and a news spec) and says that an 8k spec may carry score_min, score_max or guidance only when
every item is among `READ_ITEMS_8K`, and that guidance is a list. That moved the prompt's sha (release 1019e's
2203fda3... to 8294fe77...): a stored answer under the old sha is never read by this code (it stays stored, and its
cost stays counted in its night's cap and its day's line), and a night run by this code asks under the new sha.

THE ONE RE-RUN OF AN EMPTY NIGHT (A95; `rerun_due`, the House's lane): every births receipt records the running
`PARSE_VERSION` (4 from release 1019h: its SUP-3 moved the prompt's sha to 890806ff... at 3, and its A109's model,
part of the sha's spec, moved it again, to 0cae215b...; 2 before it; release 1019e's record none, read as 1). When the
latest night's receipts accepted none and registered none and were all written by an older version, the House runs
that night's job once more (its receipt says `rerun`), before 12:55Z of the session day after the night: it reuses the
night's stored answer when its prompt sha is
the running one (no call), else makes the night's call inside `NIGHT_USD` (the first call counts) and the lane's line.
A re-run birth is registered like any (the later of GitHub's commit time and the House's receipt), so it counts only
events knowable after the re-run; `rerun_due` says why the cut-off is safe either way.

REGISTRATION (`register`): the accepted specs' canonical lines are appended to `docs/births/<night>.jsonl` on main
through the gateway's GitHub docs route (`POST /v1/github/docs`, gateway/lib/desk.mjs: that path pattern, appends of
JSON lines only, the runtime token, a size cap). The registration time is the LATER of GitHub's commit time (the
receipt's `committed_at`) and the House's receipt of the answer, stored in `births` (league/events/store.py): a birth
counts only events knowable after it. An answer that never came (a 5xx: the commit may stand) leaves the night's
lines `unknown`, posted again the next night (`reconcile`): the route answers `unchanged` with the latest commit of the
file when they stand already, whose time is later than the true one (the reading that counts fewer events).

The CAPTAIN's births go through the same validator and registration (`night(..., proposals=...)`, the CLI's
`python -m league.events --state DIR births --specs FILE`), with no model call. The House's lane runs `night` after
the night's report (league/events/house.py, `events.births` in league/config.json). Standard library only.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import functools
import hashlib
import json
import math
import re
import sqlite3
import urllib.error
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import gw as G
from . import programs as P
from . import pxstore as PXS
from . import screen as SN
from . import store as S
from . import verdicts as V

GRAMMAR = 1
FIELDS = ("id", "version", "family", "rule", "entry", "exit", "hold", "rank", "seatable")
FAMILIES = ("ern", "ern-react", "8k", "ins", "ins-buy", "news", "news-day", "news-react")
#: Each family's entry, as the lane's decisions read it (league/events/run.py: the open decision's windows feed ern, 8k,
#: ins, ins-buy and news; the close decision's ern-react, news-day and news-react).
ENTRY = {"ern": "open", "8k": "open", "ins": "open", "ins-buy": "open", "news": "open",
         "ern-react": "close", "news-day": "close", "news-react": "close"}
RULE_FIELDS: dict[str, tuple[str, ...]] = {
    "ern": ("score_min", "score_max", "guidance"),
    "ern-react": ("score_min", "score_max", "react_min", "react_max"),
    "8k": ("items", "score_min", "score_max", "guidance"),
    "ins": ("value_min",),
    "ins-buy": ("value_min", "roles"),
    "news": ("score_min", "score_max", "sources", "hours"),
    "news-day": ("score_min", "score_max", "sources", "hours"),
    "news-react": ("react_min", "react_max", "sources", "hours"),
}
RANKS: dict[str, tuple[str, ...]] = {
    "ern": ("score", "none"), "ern-react": ("reaction", "score", "none"), "8k": ("score", "none"),
    "ins": ("value", "none"), "ins-buy": ("value", "none"), "news": ("score", "none"), "news-day": ("score", "none"),
    "news-react": ("reaction", "none"),
}
NEWS_FAMILIES = ("news", "news-day", "news-react")
REACT_FAMILIES = ("ern-react", "news-react")
#: The 8-K items a birth of the 8k family may name (EDGAR's list; 2.02 is the ern family's).
ITEMS_8K = ("1.01", "1.02", "1.03", "1.04", "1.05", "1.06", "2.01", "2.03", "2.04", "2.05", "2.06", "3.01", "3.02",
            "3.03", "4.01", "4.02", "5.01", "5.02", "5.03", "5.04", "5.05", "5.06", "5.07", "5.08", "6.01", "6.02",
            "6.03", "6.04", "6.05", "6.06", "6.10", "7.01", "8.01", "9.01")
#: The 8-K items whose PROMPT-DOC verdicts the lane asks (league/events/run.py `needs_verdict`, PREREG-EVL-1's 8K-READ):
#: a READ birth of the 8k family names only these, so its verdicts are stored (and waited for) before its decision.
READ_ITEMS_8K = tuple(sorted(P.OTHER_ITEMS))
SCORE_RANGE = (-3, 3)
REACT_MIN_RANGE = (1.01, 1.25)
REACT_MAX_RANGE = (0.75, 0.99)
VALUE_MAX = 10_000_000
ROLES = ("director", "officer")
SOURCE_RE = re.compile(r"[a-z0-9][a-z0-9._ -]{0,31}")
ID_PREFIX = "EVL-B-"
ID_RE = re.compile(r"EVL-B-[A-Z0-9]{1,12}(?:-[A-Z0-9]{1,12}){0,4}")
ID_MAX = 40
CONTROL_SUFFIX = "-CTRL"
#: THE GRAMMAR'S READING VERSION (A95, the captain's, 02:25Z Oct 22, 2026): what the running parser and prompt are,
#: recorded in every births receipt (`night`, `parse_version`). 1 is R3 as release 1019e shipped it (its receipts record
#: none: `PARSE_VERSION_BEFORE`); 2 names an id that lacks "EVL-B-" canonically (`canonical_name`), reads a one-role list
#: as its role and shows the prompt's two valid examples and its 8k line; 3 (release 1019h, the captain's A97, SUP-3's
#: rate rule) reads a seatable birth's rate over the sessions holding a complete record pass (so a store whose calendar
#: holds fewer than 20 sessions may accept one) and tells the proposer both rates and "no earnings-only family after Nov
#: 6"; 4 (release 1019h too, the captain's A109) asks Claude Opus 5.5 (`MODEL`), a new architect whose answer may be
#: accepted where Haiku 4.5's was refused, and the model is part of `prompt_sha`'s spec, so the sha moved again (3 was
#: never live: release 1019h ships both); 5 (release 1019i, PREREG-EVL-6 section 5) tells the proposer the restated
#: charge from the budget (`<<CHARGE>>`: 0.13 a seatable spec, where version 4's text said 0.10) and the validator
#: charges 0.13 of the restated 3.9, a birth only with room left after every run waiting for the budget. A night whose
#: receipt is older than this and accepted and registered none is run ONCE more (`rerun_due`). It moves with any change
#: of `parse`, of the validator, of the prompt or of the model that could turn a refused answer into an accepted one,
#: and with any change of the prompt's text (the prompt's sha and this version are pinned together:
#: league/tests/test_events_births_names.py).
PARSE_VERSION = 5
PARSE_VERSION_BEFORE = 1
#: A night's one re-run starts before this UTC time of the session day after the night (A95): the start of the
#: deploy-blocked session window (12:55Z, 08:55 ET in daylight time and 07:55 ET in standard time), at least 5 (65)
#: minutes before that session's 09:00 ET cut-off and 20 (80) before its 09:15 ET open decision.
RERUN_BY = dt.time(12, 55)
#: How far back the re-run looks for a night's receipts (a long weekend's Friday night is the oldest that can be due).
RERUN_REACH = dt.timedelta(days=10)

#: THE VALIDATOR'S RULES (R3-SPEC sections 2 and 3).
SESSIONS = 20
#: THE RATE A SEATABLE BIRTH MUST SELECT (SUP-3's rate rule, the captain's A97, release 1019h; R3-SPEC is the captain's,
#: no frozen text names it): at least `MIN_RATE` selected events a session, over THE SESSIONS OF THE LAST `SESSIONS`
#: THAT HOLD A COMPLETE RECORD PASS (`recorded_sessions`: an outage session is left out, never counted at a low count),
#: at least `MIN_RECORDED` of them. A seatable birth must fill a Probe row's slots after the real-money funnel, through
#: the season; release 1019e's 3 over the calendar's 20 fell toward 3 a session as the window filled.
MIN_RATE = 20
MIN_RECORDED = 3
#: A RECORD (`seatable` false) keeps release 1019e's rate, free as before: `RECORD_MIN_RATE` a session over the
#: calendar's last `SESSIONS` sessions (the store must hold them all).
RECORD_MIN_RATE = 3
JACCARD_MAX = 0.8
#: The false-pass budget (A81 as PREREG-EVL-6 section 5 restates it, D6 and D11), in HUNDREDTHS of an expected false
#: pass (integers: no float drift), read from the screen and never restated here: each seatable birth the screen's
#: charge, V6_CHARGE_HUNDREDTHS, 13 (0.13: every birth registered from REGISTERED_AT_6 on is judged by PREREG-EVL-6,
#: section 1.1's LATER VERSIONS); every charge the lane ever makes (each PREREG-EVL-6 version's run 1 and each fresh run
#: when it starts) at most the lane's restated lifetime budget, V6_BUDGET_HUNDREDTHS, 390 (3.9); what is used is the
#: screen's own count (`budget_used_hundredths`: the fifteen new versions, 195, before any birth or fresh run); a birth
#: registers only when the room left AFTER EVERY RUN WAITING FOR THE BUDGET holds its charge (section 3); at most 3
#: seatable births a night. (PREREG-EVL-3's and -4's 0.10 a version and 3.0 are the record before PREREG-EVL-6.)
CHARGE_HUNDREDTHS = SN.V6_CHARGE_HUNDREDTHS
BUDGET_HUNDREDTHS = SN.V6_BUDGET_HUNDREDTHS
#: (the earlier names, in tenths, kept for readers of release 1019h's receipts: 0.13 and 3.9 are not whole tenths, so
#: nothing here charges in them)
CHARGE_TENTHS = int(round(SN.FALSE_PASS_RATE * 10))
BUDGET_TENTHS = int(round(SN.LANE_BUDGET * 10))
SEATABLE_A_NIGHT = 3
#: THE CHARGES OF FROZEN FILES WHOSE CODE IS NOT LIVE YET (the captain's A137): (file, its pin in league/events/programs.py,
#: hundredths). The screen's own sum (`budget6`) counts only what this code registers, so without this a frozen file's
#: reservation (PREREG-EVL-8's five seats at 0.13 a run, A122; PREREG-EVL-9's 0.30 reserved at registration, A127)
#: would be spent by births before its code ships, and the lane's stated 3.9 overrun. Each is held from the births'
#: room while its pin is unset and released when its release pins it (its own versions are then counted by the
#: screen). PREREG-EVL-10's 0.13 is held in A129's order (the captain's budget order: READER-2's seat before more
#: seatable births). Records stay free.
RESERVED = (("PREREG-EVL-8", "REGISTERED_AT_8", 65), ("PREREG-EVL-9", "REGISTERED_AT_9", 30),
            ("PREREG-EVL-10", "REGISTERED_AT_10", 13))

#: THE PROPOSER (R3-SPEC section 2). THE ARCHITECT (the captain's A109, 06:05Z Oct 22, 2026; release 1019h): Claude
#: Opus 5.5, in the gateway's CLAUDE_MODELS allowlist (gateway/wrangler.jsonc; a model absent from it is a 403). Release
#: 1019e to 1019g asked the verdict reader's model, Haiku 4.5 (`V.MODEL`, which stays the verdicts' own).
MODEL = "claude-opus-5-5"
#: THE CALL'S FORM FOR OPUS 5.5 (A109 as built): Claude Opus 5.5 takes NO SAMPLING PARAMETER (`temperature` is
#: Anthropic's own 400, unbilled: gateway/lib/claude.mjs's note on `temperature`, and a 4xx is never asked again, so a
#: body with release 1019g's temperature 0 would have proposed nothing every night); the body carries none (`None`:
#: omitted). The answer is not sampled deterministically, but a night's answer is still asked once, stored and read
#: again (`birth_calls`), so the record is the store's, never a re-ask. Opus 5.5 ALWAYS THINKS (adaptive; thinking
#: cannot be disabled, its default effort is "medium") and its thinking is OUTPUT inside `max_tokens`: `EFFORT` "low"
#: keeps the thinking short (the call is streamed, `STREAM` below: release 1019h's first build sent it unstreamed,
#: whose answer could outlast both the lane client's 45-second read and Cloudflare's 100-second wait), and `MAX_TOKENS`
#: 6000 (3000 to release 1019g, Haiku's, which never thinks here) leaves the six specs' answer (about 1,000-1,500 tokens)
#: room after the thinking, while the worst case stays inside the night's $0.25 (`worst_usd`: $0.132 out at $22 a
#: million, the rest for the prompt). An answer cut at `max_tokens` is stored as `cut` (`propose`), never as `ok`.
TEMPERATURE: int | None = None
EFFORT = "low"
MAX_TOKENS = 6000
#: THE CALL IS STREAMED (release 1019h's fix round, the money and rules reviews of A109): an unstreamed answer comes back
#: only when Anthropic has finished it (the gateway awaits the whole body), so the House's socket would hear nothing for
#: the whole generation, and the lane's gateway client waits 45 s a read (league/events/gw.py), under what a thinking
#: Opus answer can take (the reviews' estimate: 1,750-4,500 tokens out at 50-80 a second, 22-90 s; not yet measured on
#: the House: the deploy records the first night's seconds beside its cost; Cloudflare's 100-second wait in front
#: of api.anthropic.com cuts an unstreamed one with a 524). Streamed (`request_body`: `stream` true, the thinking
#: `summarized` so its deltas keep the bytes flowing while the model thinks; display changes what is shown, never what
#: is billed), the gateway relays Anthropic's events as they come and ends with its own cost (league/events/gw.py
#: `post_stream`). The socket waits at most `STREAM_GAP` for a byte and the whole answer at most `CALL_LIMIT`; on the
#: House the call starts only with both left before the births job's bound (league/events/house.py `LaneGateway`
#: `post_stream`, BIRTHS_BUDGET 240 s), so it never runs past the job. The stream and the display are not in the prompt
#: sha's spec (`prompt_sha`): they change how the answer arrives, not what is asked.
STREAM = True
THINKING = {"type": "adaptive", "display": "summarized"}
CALL_LIMIT = 150.0
STREAM_GAP = 60.0
#: WHAT A NIGHT'S CALL ENDED AS (`propose`), stored in `birth_calls` with its cost: `ok` (an answer, parsed), `cut` (cut
#: at max_tokens), `refused` (stop_reason refusal) and `lost`: THE CALL WENT OUT AND NO WHOLE ANSWER CAME BACK (a stream
#: that broke, went quiet or ran past CALL_LIMIT; no answer while waiting for one; a 5xx the gateway did not settle; an
#: error the gateway settled at a cost). A lost call may still run and be billed, so it is NEVER ASKED AGAIN that night
#: (the gateway does not refuse a repeated request id) and its row counts the gateway's stated cost when the gateway read
#: the usage, else the call's WORST CASE (`worst_usd`: unknown is not free), in the night's cap, the lane's line, the
#: budget rule's measure of the lane and the site's bill. Not stored (`no answer`): a call the lane refused before it
#: went out (league/events/house.py `LaneCut`, `G.NotSent`), one whose request never reached the gateway (urllib's
#: `URLError`), and errors the gateway settled at nothing; only those, a 429 and a 5xx the gateway settled may be asked
#: once more. A night whose call ended `no answer`, `lost`, `cut` or `refused` finishes its receipt `unanswered`
#: (`night`): the House warns (league/events/house.py `_births`) and the report lists it among the failed jobs.
LOST = "lost"
#: A CALL WRITTEN AHEAD OF ITS SEND (release 1019h's re-review, a minor fixed in release 1019i): `propose` writes the
#: night's `birth_calls` row BEFORE the call goes out, `asked` at the call's worst case (its `answered_at` the asking
#: time, so every reader of the day's spend counts it), and turns it into the call's end by an UPDATE. A House that
#: restarts mid-call leaves the row `asked`: counted at its worst case, never $0, and never asked again that night (a
#: later run reads it as stored, `stored:asked`). A call refused before it went out deletes its row (nothing billed).
ASKED = "asked"
UNANSWERED = ("no answer", LOST, "cut", "refused", ASKED)
K = 6
NIGHT_USD = 0.25
#: THE MODEL'S OWN PRICES (A109): USD a million tokens, the gateway's CLAUDE_MODELS row of `MODEL`
#: (gateway/wrangler.jsonc, the price table and the allowlist; a test holds the two equal): its uncached input (the call
#: marks no cache), its output, and its inference geographies' multipliers. The gateway settles a call at the
#: geography Anthropic reports (Claude 4.6 and later bill US-only inference at 1.1x every rate, and a workspace whose
#: default geography is "us" is billed so without asking) and reserves at the dearest, so the worst case prices every
#: token at the dearest too (`GEO_MAX`), as league/claude.py's ceilings do: never under what the night can be billed.
PRICES = {"input": 4.0, "output": 20.0, "geo": {"us": 1.1}}
GEO_MAX = max([1.0, *PRICES["geo"].values()])
PRICE_IN = PRICES["input"] * GEO_MAX / 1_000_000     # USD a token in: Claude Opus 5.5 at $4, x1.1 US-only ($4.40)
PRICE_OUT = PRICES["output"] * GEO_MAX / 1_000_000   # USD a token out: $20, x1.1 ($22)
CHARS_A_TOKEN = 3                   # the cap's worst case counts a token every 3 characters (JSON runs nearer 3.5)
WHY_MAX = 200
DOCS_ROUTE = "/v1/github/docs"
DOCS_DIR = "docs/births"
#: The births job's receipt (league/events/house.py runs it once a session night, after the report).
JOB = "births"
EPOCH = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
#: What the facts may never read (R3-SPEC section 2): a price after an event, a return, a P&L, a look's p, a band.
FACTS_DENY = frozenset({"bars", "marks", "outcomes", "looks", "bands", "band_history", "real_fills", "universe", "meta"})
#: RELEASE 1019i: the attempts ledger (`real_attempts`: the venue's fill prices and states, PREREG-EVL-7's H6) and the
#: batched score's parity flags (`score_parity`: one per settled intent) are outcome-derived: the facts never read them.
FACTS_DENY = FACTS_DENY | frozenset({"real_attempts", "score_parity"})
#: ... and every table of the price lane's store (league/events/pxstore.py `TABLES`: SIP bars, minute marks, the flags,
#: the PX universe's prices and the decided values): px.sqlite is a file of its own, which the facts never open, and
#: each of its tables is refused by name as well.
FACTS_DENY = FACTS_DENY | PXS.TABLES
#: THE CLOSE-ENTRY FAMILIES OF PREREG-EVL-4 AND -5 (release 1019h, the module docstring's "PREREG-EVL-4'S AND
#: PREREG-EVL-5'S FAMILIES"): no birth names one (the grammar's `FAMILIES` stay R3's), but the facts window them, so each
#: of their programs has a selection count and every candidate a Jaccard against them.
FILE_FAMILIES = tuple(P.CLOSE_FAMILIES_4) + tuple(P.CLOSE_FAMILIES_5)
#: The facts' unread reaction of PREREG-EVL-5's two earnings families (a price after the event, never read): a value
#: inside each row's own band, so every event passes it (an upper bound, as `unread_reaction` is for the react
#: families): EVL-ERN-DROP-ON's <= 0.96; EVL-ERN-UNDER-ON's and its control's above 0.96 and below 1.04.
UNREAD_IN_BAND = {"ern-drop": P.DROP_RATIO, "ern-under": 1.0}
#: PREREG-EVL-7 (section 9, the task's item 5): the learners' outcome-derived state and COST-7's tables never reach the
#: facts (league/events/learner.py `TABLES`: learner_fits, learner_cands and the per-session sums; league/events/
#: costs7.py `TABLES`: costs7 and cost_basis), nor the intents, whose `rank_key` holds a learner's fitted ahat (check
#: 2's minor 10 (3): the facts never read intents).
FACTS_DENY = FACTS_DENY | frozenset({"learner_fits", "learner_cands", "learner_stats", "costs7", "cost_basis", "intents"})


class SpecError(ValueError):
    """A spec the grammar refuses, with every reason."""

    def __init__(self, reasons: Sequence[str]):
        self.reasons = [str(r) for r in reasons] or ["refused"]
        super().__init__("; ".join(self.reasons))


# ----------------------------------------------------------------------------------------------------------- grammar
def _int(value: Any) -> bool:
    return type(value) is int


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def canonical_name(ident: Any) -> Any:
    """THE HOUSE'S NAME of a proposed id (A95): a name is not part of the rule, so an id that lacks the "EVL-B-" prefix
    is named canonically, a leading "EVL-" becoming "EVL-B-" and any other id taking "EVL-B-" in front ("EVL-ERN-NEG-O1"
    is "EVL-B-ERN-NEG-O1", "ERN-NEG" is "EVL-B-ERN-NEG"). Every check of an id (ID_RE, ID_MAX, never ending "-CTRL",
    never registered) applies to the new name. An id with the prefix, or one that is not a string, is as it was."""
    if not isinstance(ident, str) or ident.startswith(ID_PREFIX):
        return ident
    return ID_PREFIX + (ident[len("EVL-"):] if ident.startswith("EVL-") else ident)


def _raw(spec: Any) -> Any:
    if isinstance(spec, (str, bytes, bytearray)):
        try:
            return json.loads(spec)
        except ValueError:
            return None
    return spec


def renamed(spec: Any) -> dict[str, str] | None:
    """{from, to}: the proposed id and the House's name for it (`canonical_name`) when they differ, else None (a spec
    that is not a JSON object, or whose id is not a string, has none). The candidate row keeps it (`night`)."""
    raw = _raw(spec)
    ident = raw.get("id") if isinstance(raw, Mapping) else None
    if not isinstance(ident, str) or canonical_name(ident) == ident:
        return None
    return {"from": ident, "to": canonical_name(ident)}


def parse(spec: Any) -> dict[str, Any]:
    """The spec in its normal form (lists sorted, sources lower-cased, ratios to 4 places, the House's canonical name
    of its id, a one-role list as its role), or SpecError with every reason: the GRAMMAR's fields and only those, each
    of its type and bounds, the family's rule fields and only those."""
    if isinstance(spec, (str, bytes, bytearray)):
        try:
            spec = json.loads(spec)
        except ValueError:
            raise SpecError(["a spec is a JSON object"]) from None
    if not isinstance(spec, Mapping):
        raise SpecError(["a spec is a JSON object"])
    why: list[str] = []
    extra = sorted(str(k) for k in spec if k not in FIELDS)
    missing = [f for f in FIELDS if f not in spec]
    if extra:
        why.append(f"fields outside the grammar: {', '.join(extra)}")
    if missing:
        why.append(f"missing fields: {', '.join(missing)}")
    if why:
        raise SpecError(why)
    out: dict[str, Any] = {}
    ident = canonical_name(spec["id"])      # (A95: the House names an id that lacks "EVL-B-"; the checks are the name's)
    if not isinstance(ident, str) or len(ident) > ID_MAX or not ID_RE.fullmatch(ident) or ident.endswith(CONTROL_SUFFIX):
        named = f" (the House's name {ident} of {spec['id']})" if ident != spec["id"] else ""
        why.append(f"id must match EVL-B-<A-Z0-9 groups>, at most {ID_MAX} characters, never ending {CONTROL_SUFFIX}"
                   + named)
    out["id"] = ident
    if not _int(spec["version"]) or spec["version"] != 1:
        why.append("version must be 1 (a change is a new birth)")
    out["version"] = 1
    family = spec["family"]
    if family not in FAMILIES:
        raise SpecError(why + [f"family must be one of {', '.join(FAMILIES)}"])
    out["family"] = family
    if spec["entry"] != ENTRY[family]:
        why.append(f"the {family} family enters at the {ENTRY[family]}")
    out["entry"] = ENTRY[family]
    exit_ = spec["exit"]
    if exit_ not in ("close", "open"):
        why.append("exit must be close or open")
    elif ENTRY[family] == "open" and exit_ != "close":
        why.append("an open entry exits at a close")
    out["exit"] = exit_
    hold = spec["hold"]
    if not _int(hold) or not 1 <= hold <= 5:
        why.append("hold must be an integer 1..5")
    out["hold"] = hold
    seatable = spec["seatable"]
    if type(seatable) is not bool:
        why.append("seatable must be true or false")
    elif seatable and hold != 1:
        why.append("a seatable birth holds one session (the screen's blocks are one-session blocks); a longer hold is a "
                   "record")
    if seatable is True and spec.get("family") == "ins":
        # A89 (the captain's, release 1019e's last review): a Form 4 CLUSTER is judged over every Form 4 of the issuer in
        # its window, and real money may only read filings stored before its decision (A72); the House's book cannot
        # read a cluster that way yet, so an `ins` birth is a record (free, shadow only), never seatable.
        why.append("an ins (Form 4 cluster) birth is a record only: real money cannot read a cluster stored before its "
                   "decision (A89); register it seatable false")
    out["seatable"] = seatable
    rank = spec["rank"]
    if rank not in RANKS[family]:
        why.append(f"rank must be one of {', '.join(RANKS[family])} for the {family} family")
    out["rank"] = rank
    rule = spec["rule"]
    if not isinstance(rule, Mapping):
        raise SpecError(why + ["rule must be a JSON object"])
    allowed = RULE_FIELDS[family]
    odd = sorted(str(k) for k in rule if k not in allowed)
    if odd:
        why.append(f"rule fields outside the {family} family's ({', '.join(allowed)}): {', '.join(odd)}")
    norm: dict[str, Any] = {}
    for name in ("score_min", "score_max"):
        if name in rule:
            v = rule[name]
            if not _int(v) or not SCORE_RANGE[0] <= v <= SCORE_RANGE[1]:
                why.append(f"{name} must be an integer -3..3 (the stored verdict's score)")
            norm[name] = v
    if _int(norm.get("score_min")) and _int(norm.get("score_max")) and norm["score_min"] > norm["score_max"]:
        why.append("score_min is above score_max: the rule selects nothing")
    if "guidance" in rule:
        g = rule["guidance"]
        if not isinstance(g, list) or not g or any(x not in V.GUIDANCE for x in g) or len(set(g)) != len(g) or \
                len(g) == len(V.GUIDANCE):
            why.append(f"guidance must be a proper subset of {', '.join(V.GUIDANCE)}, without repeats")
        else:
            norm["guidance"] = sorted(g)
    if "items" in rule:
        items = rule["items"]
        if not isinstance(items, list) or not items or any(x not in ITEMS_8K for x in items) or len(set(items)) != len(items):
            why.append("items must be a list of 8-K items (EDGAR's, never 2.02: that is the ern family), without repeats")
        else:
            norm["items"] = sorted(items)
    for name, (lo, hi) in (("react_min", REACT_MIN_RANGE), ("react_max", REACT_MAX_RANGE)):
        if name in rule:
            v = rule[name]
            if not _number(v) or not lo <= float(v) <= hi or round(float(v), 4) != float(v):
                why.append(f"{name} must be a ratio in {lo}..{hi} with at most 4 decimals")
            else:
                norm[name] = round(float(v), 4)
    if "value_min" in rule:
        v = rule["value_min"]
        floor = P.INS_MIN_VALUE if family == "ins" else P.INS_BUY_MIN_VALUE
        if not _int(v) or not floor <= v <= VALUE_MAX:
            why.append(f"value_min must be whole dollars {int(floor)}..{VALUE_MAX} (the lane reads no smaller Form 4)")
        norm["value_min"] = v
    if "roles" in rule:
        role = rule["roles"]
        if isinstance(role, list) and len(role) == 1 and isinstance(role[0], str) and role[0] in ROLES:
            role = role[0]      # (A95: a one-role list reads as its role; any other list is refused)
        if not isinstance(role, str) or role not in ROLES:
            why.append("roles must be director or officer (no role filter: leave it out)")
        norm["roles"] = role
    if "sources" in rule:
        src = rule["sources"]
        if not isinstance(src, list) or not 1 <= len(src) <= 8 or any(not isinstance(x, str) for x in src):
            why.append("sources must be 1..8 news source names")
        else:
            low = [x.strip().lower() for x in src]
            if any(not SOURCE_RE.fullmatch(x) for x in low) or len(set(low)) != len(low):
                why.append("a source name is 1..32 of a-z, 0-9, '.', '_', '-' and spaces, without repeats")
            norm["sources"] = sorted(set(low))
    if "hours" in rule:
        hours = rule["hours"]
        if not isinstance(hours, list) or not 1 <= len(hours) <= 23 or any(not _int(h) or not 0 <= h <= 23 for h in hours) \
                or len(set(hours)) != len(hours):
            why.append("hours must be 1..23 distinct New York hours 0..23")
        else:
            norm["hours"] = sorted(hours)
    if family == "8k":
        if "items" not in rule:
            why.append("the 8k family names its item set (items)")
        elif "items" in norm and _reads(norm, rank) and not set(norm["items"]) <= set(READ_ITEMS_8K):
            why.append(f"a READ birth of the 8k family names only items whose verdicts the lane asks "
                       f"({', '.join(READ_ITEMS_8K)})")
    if family in REACT_FAMILIES and "react_min" not in rule and "react_max" not in rule:
        why.append("a react family names react_min or react_max")
    if "react_min" in norm and "react_max" in norm:
        why.append("react_min and react_max together select nothing (one is above 1, the other below)")
    if why:
        raise SpecError(why)
    out["rule"] = norm
    return out


def _reads(rule: Mapping[str, Any], rank: Any) -> bool:
    return any(k in rule for k in ("score_min", "score_max", "guidance")) or rank == "score"


def reads(spec: Mapping[str, Any]) -> bool:
    """A READ birth: it reads a stored verdict (a threshold, a guidance filter or a score ranking)."""
    return _reads(spec.get("rule") or {}, spec.get("rank"))


def canonical(spec: Any) -> str:
    """The canonical form: the parsed spec as JSON, keys sorted, no spaces, ASCII."""
    return json.dumps(parse(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(spec: Any) -> str:
    return hashlib.sha256(canonical(spec).encode("ascii")).hexdigest()


def control_id(birth_id: str) -> str:
    return f"{birth_id}{CONTROL_SUFFIX}"


def control_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """A READ birth's CONTROL (PREREG-EVL-1 section 7's beat-the-control rule): the same rule with every verdict
    condition removed (thresholds, guidance, a score ranking), a record with the id "<id>-CTRL". Derived, so it is
    registered with its birth, at the same time."""
    rule = {k: v for k, v in (spec.get("rule") or {}).items() if k not in ("score_min", "score_max", "guidance")}
    rank = "none" if spec.get("rank") == "score" else spec.get("rank")
    return dict(spec) | {"id": control_id(str(spec["id"])), "rule": rule, "rank": rank, "seatable": False}


@functools.lru_cache(maxsize=512)
def _spec_of(text: str) -> dict[str, Any]:
    """A Program's spec (its canonical JSON, or a control's derived JSON), parsed once."""
    data = json.loads(text)
    if str(data.get("id", "")).endswith(CONTROL_SUFFIX):
        return data
    return parse(data)


def program(spec: Mapping[str, Any], *, born_at: str) -> P.Program:
    """The Program row of a parsed spec (a birth or a derived control), registered at `born_at` (ISO UTC):
    PREREG-EVL-3's learning band, screen and limit at entry (prereg 3), its own rule (`spec`)."""
    text = json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return P.Program(str(spec["id"]), int(spec["version"]), bool(spec["seatable"]), str(spec["family"]),
                     str(spec["entry"]), int(spec["hold"]), reads(spec), exit_at=str(spec["exit"]), rule="birth",
                     prereg=3, born_at=S.iso(S.parse_iso(born_at)), spec=text)


def _tables(db: Any) -> set[str]:
    return {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def registered_programs(store: Any) -> list[P.Program]:
    """Every registered birth of `store`'s `births` table as Program rows, in registration order (its time, then its
    line in the night's file), a READ birth followed by its control. A row whose spec this grammar no longer parses, or
    whose sha is not its spec's, is left out (it seats nothing). No table: none."""
    if "births" not in _tables(store.db):
        return []
    out: list[P.Program] = []
    for row in store.db.execute("SELECT id, sha, spec, registered_at FROM births ORDER BY registered_at, night, seq, id"):
        try:
            spec = parse(str(row["spec"]))
            if sha(spec) != str(row["sha"]):
                continue
            prog = program(spec, born_at=str(row["registered_at"]))
        except (SpecError, ValueError, TypeError, KeyError):
            continue
        out.append(prog)
        if prog.reads:
            out.append(program(control_spec(spec), born_at=str(row["registered_at"])))
    return out


# ----------------------------------------------------------------------------------------------------------- the rule
def unread_reaction(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float:
    """The facts' reaction: never read (a price after the event). Every event passes it, so a react rule's count is an
    upper bound (PREREG's own REACT rule, ratio >= 1.04, passes infinity too)."""
    return math.inf


def unread_gap(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float:
    """The facts' gap of EVL-NEWS-NIGHT2-ON (D's 09:30 minute over P's close: a price after the attention article):
    never read; every event passes it (an upper bound, release 1019h)."""
    return math.inf


def facts_reaction(prog: P.Program) -> Callable[[Mapping[str, Any], Mapping[str, Any]], float]:
    """The facts' unread reaction for `prog` (release 1019h): `unread_reaction` for every birth and every react family;
    for PREREG-EVL-5's earnings rows a value inside the row's own band (`UNREAD_IN_BAND`), so each event passes it."""
    if prog.spec is None and prog.family in UNREAD_IN_BAND:
        value = UNREAD_IN_BAND[prog.family]
        return lambda row, uni: value
    return unread_reaction


def select(program: P.Program, rows: Iterable[Mapping[str, Any]], *,
           eligible: Callable[[str], Mapping[str, Any] | None], verdict: Callable[[Mapping[str, Any]], int | None],
           reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None,
           guidance: Callable[[Mapping[str, Any]], str | None] | None = None) -> list[P.Candidate]:
    """A birth's candidates from already-windowed event rows (league/events/programs.py `select` hands a birth here,
    with the same callables): the family's events knowable after the birth's own registration time, its rule's filters,
    an eligible issuer (a news article's symbol the eligible one), the stored verdict's score and guidance when it reads
    them (an event with none is not taken, as a PREREG READ program's), the reaction when its family has one (an event
    with no reading is not taken; `unread_reaction`: the facts' upper bound, never a price); ranked by its rank key; a
    news family one article an issuer (the highest score, then the earliest, when it ranks by score; else the
    earliest)."""
    spec = _spec_of(str(program.spec))
    family, rule, rank_by = str(spec["family"]), dict(spec["rule"]), str(spec["rank"])
    wants_score = any(k in rule for k in ("score_min", "score_max")) or rank_by == "score"
    unread = reaction is unread_reaction
    since = program.registered_at
    out: list[P.Candidate] = []
    for row in rows:
        knowable = S.parse_iso(row.get("knowable_at"))
        if knowable <= since:
            continue
        value = None
        if family in ("ern", "ern-react", "8k"):
            items = P.items_of(row)
            if family == "8k":
                if items & P.ERN_ITEMS or not items & set(rule["items"]):
                    continue
            elif not items & P.ERN_ITEMS:
                continue
            event = f"8k:{row['accession']}"
        elif family in ("ins", "ins-buy"):
            event = f"f4:{row['accession']}"
            value = float(row.get("cluster_value" if family == "ins" else "purchase_value") or 0.0)
            if value < float(rule.get("value_min", 0)):
                continue
            if family == "ins-buy" and rule.get("roles") and not row.get(f"by_{rule['roles']}"):
                continue
        else:
            event = f"news:{row['id']}"
            if "sources" in rule and str(row.get("source") or "").strip().lower() not in rule["sources"]:
                continue
            if "hours" in rule and knowable.astimezone(C.NY).hour not in rule["hours"]:
                continue
        cik = row.get("cik") or row.get("issuer_cik")
        uni = eligible(cik) if cik else None
        if uni is None:
            continue
        if family in NEWS_FAMILIES and uni["symbol"] != row.get("symbol"):
            continue
        score = None
        if wants_score:
            score = verdict(row)
            if score is None:
                continue
            if "score_min" in rule and score < rule["score_min"]:
                continue
            if "score_max" in rule and score > rule["score_max"]:
                continue
        if "guidance" in rule and (guidance is None or guidance(row) not in rule["guidance"]):
            continue
        rank: float | None = float(score) if rank_by == "score" and score is not None else None
        if family in REACT_FAMILIES and not unread:
            ratio = reaction(row, uni) if reaction is not None else None
            if ratio is None:
                continue
            if "react_min" in rule and ratio < rule["react_min"]:
                continue
            if "react_max" in rule and ratio > rule["react_max"]:
                continue
            if rank_by == "reaction":
                rank = float(ratio)
        if rank_by == "value":
            rank = value
        out.append(P.Candidate(event, str(cik), uni["symbol"], knowable, rank, score, row))
    if family in NEWS_FAMILIES:
        best: dict[str, P.Candidate] = {}
        for c in out:
            have = best.get(c.cik)
            if have is None or _news_order(c, rank_by) > _news_order(have, rank_by):
                best[c.cik] = c
        out = list(best.values())
    return out


def _news_order(c: P.Candidate, rank_by: str) -> tuple[float, float]:
    """A news family's one article an issuer, as PREREG's `select` keeps it: the highest score (when the birth ranks by
    score), then the earliest; on a tie the first in the rows' order stays."""
    score = float(c.verdict_score) if (rank_by == "score" and c.verdict_score is not None) else -9.0
    return (score, -c.knowable_at.timestamp())


# ----------------------------------------------------------------------------------------------------------- the facts
_WALLED: dict[int, int] = {}


@contextlib.contextmanager
def outcome_free(db: sqlite3.Connection, deny: Iterable[str] = FACTS_DENY) -> Any:
    """Every statement on `db` inside this block is refused a read of the tables `deny` (a SQLite authorizer: a price
    after an event, a return, a P&L, a look's p or a band never reaches the facts). Nested blocks keep the outermost
    wall up until it ends; the connection reads as before after it."""
    refused = frozenset(deny)

    def authorize(action: int, arg1: Any, arg2: Any, dbname: Any, source: Any) -> int:
        if action == sqlite3.SQLITE_READ and str(arg1) in refused:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    key = id(db)
    if not _WALLED.get(key):
        db.set_authorizer(authorize)
    _WALLED[key] = _WALLED.get(key, 0) + 1
    try:
        yield db
    finally:
        _WALLED[key] -= 1
        if not _WALLED[key]:
            _WALLED.pop(key, None)
            db.set_authorizer(None)


class _Eligible:
    """The lane's kept eligibility results (`eligibility`: no price), by session: the session's own (eligible only when
    no result of it is ineligible, the backfill reading), else the issuer's nearest result (the latest before, else the
    earliest after); an issuer never judged is not eligible."""

    def __init__(self, store: Any):
        self.by_day: dict[tuple[str, str], list[tuple[int, str | None]]] = {}
        self.by_cik: dict[str, list[tuple[str, int, str | None]]] = {}
        for r in store.db.execute("SELECT day, cik, eligible, symbol FROM eligibility ORDER BY day, cik, rule"):
            day, cik = str(r["day"]), str(r["cik"])
            self.by_day.setdefault((day, cik), []).append((int(r["eligible"]), r["symbol"]))
        for (day, cik), results in sorted(self.by_day.items()):
            ok = all(e for e, _ in results)
            symbol = next((s for e, s in results if e and s), None)
            self.by_cik.setdefault(cik, []).append((day, int(ok), symbol))

    def row(self, day: dt.date, cik: Any) -> dict[str, Any] | None:
        if not cik:
            return None
        cik = str(cik)
        found = self.by_cik.get(cik)
        if not found:
            return None
        text = day.isoformat()
        exact = [x for x in found if x[0] == text]
        before = [x for x in found if x[0] < text]
        pick = exact[0] if exact else (before[-1] if before else found[0])
        return {"cik": cik, "symbol": pick[2]} if pick[1] and pick[2] else None

    def symbols(self, day: dt.date) -> dict[str, str]:
        """{symbol: cik} for news rows: each issuer's symbol as of `day` (its nearest eligible result)."""
        out: dict[str, str] = {}
        for cik in self.by_cik:
            row = self.row(day, cik)
            if row is not None:
                out.setdefault(str(row["symbol"]).upper(), cik)
        return out


def recorded_sessions(store: Any, days: Sequence[dt.date]) -> list[dt.date]:
    """THE SESSIONS OF `days` THAT HOLD A COMPLETE RECORD PASS (SUP-3's denominator, the captain's A97, release 1019h),
    oldest first: D's whole event span, from the prior session's 09:00 ET (the open window's start, the earliest of D's
    windows: league/events/programs.py `open_window`) to D's close decision (`close_window`'s end, the latest), was
    recorded with no OUTAGE: a CLEAN record pass (league/ops/evl_health.py's own reading, `_failing`: finished `ok`, its
    8-K, Form 4 and news reads without error) finished at or before the span's start within `RECORD_MINUTES` (30, the
    `evl_record` alarm's line), every two consecutive clean passes inside the span at most that far apart, and the last
    at most that far before its end. An outage session (the alarm's stall inside the span), a session before the
    recorder ran and one the calendar cannot place are left out (never counted at a low count). Reads `receipts` only
    (outcome-free: no price, return, look or band)."""
    from ..ops import evl_health as EH

    gap = dt.timedelta(minutes=EH.RECORD_MINUTES)
    spans: list[tuple[dt.date, dt.datetime, dt.datetime]] = []
    for day in days:
        d = C.session(store, day)
        prior = C.previous(store, day, 1)
        if d is None or not prior:
            continue
        spans.append((day, prior[0].open_cutoff, d.close_decide))
    if not spans or "receipts" not in _tables(store.db):
        return []
    lo, hi = min(a for _, a, _ in spans) - gap, max(b for _, _, b in spans)
    clean: list[dt.datetime] = []
    for row in store.db.execute("SELECT finished_at, status, summary FROM receipts WHERE job='record' AND status='ok' AND "
                                "finished_at IS NOT NULL AND finished_at>=? AND finished_at<=? ORDER BY finished_at",
                                (S.iso(lo), S.iso(hi))):
        try:
            at = S.parse_iso(str(row["finished_at"]))
        except (TypeError, ValueError):
            continue
        if not EH._failing({"summary": row["summary"]}):
            clean.append(at)
    clean.sort()
    out: list[dt.date] = []
    for day, start, end in spans:
        inside = [t for t in clean if start - gap <= t <= end]
        if not inside or inside[0] > start or end - inside[-1] > gap:
            continue
        if all(b - a <= gap for a, b in zip(inside, inside[1:])):
            out.append(day)
    return out


class Facts:
    """THE OUTCOME-FREE FACTS of the last `sessions` sessions through `today` (the module docstring): the event rows of
    each session's windows as the lane's decisions read them (registration aside: a rule's count is what it WOULD have
    selected), the kept eligibility, the stored verdicts. Built and read inside `outcome_free`: a read of a refused
    table raises. `facts()` is the architect's JSON; `selected(program)` a program's selected events by session."""

    def __init__(self, store: Any, today: dt.date, *, sessions: int = SESSIONS):
        self.store = store
        self.today = today
        with outcome_free(store.db):
            self.days = [s.day for s in C.previous(store, today + dt.timedelta(days=1), sessions)]
            self.elig = _Eligible(store)
            self.scores: dict[str, tuple[int, str | None]] = {}
            doc, news = V.PROMPTS["doc"].sha, V.PROMPTS["news"].sha
            for r in store.db.execute("SELECT event, prompt_sha, score, guidance FROM verdicts WHERE model=? AND "
                                      "status='ok' AND prompt_sha IN (?, ?)", (V.MODEL, doc, news)):
                kind = "doc" if r["prompt_sha"] == doc else "news"
                self.scores[f"{kind}|{r['event']}"] = (int(r["score"]), r["guidance"] if kind == "doc" else None)
            self.rows = {day: self._windows(day) for day in self.days}
            self.recorded = recorded_sessions(store, self.days)
        self._selected: dict[str, dict[dt.date, list[str]]] = {}

    @property
    def complete(self) -> bool:
        """The calendar holds the window's `SESSIONS` sessions (a record's rate is read over them)."""
        return len(self.days) >= SESSIONS

    @property
    def rated(self) -> bool:
        """At least `MIN_RECORDED` of the window's sessions hold a complete record pass (a seatable birth's rate is read
        over them, `recorded`)."""
        return len(self.recorded) >= MIN_RECORDED

    def rate(self, prog: P.Program) -> tuple[int, float]:
        """(the events `prog` selects on the window's sessions holding a complete record pass, that a session over
        them; 0.0 with none): a seatable birth's rate (`MIN_RATE`)."""
        by = self.selected(prog)
        n = sum(len(by.get(day, ())) for day in self.recorded)
        return n, (round(n / len(self.recorded), 2) if self.recorded else 0.0)

    def _windows(self, day: dt.date) -> dict[str, list[Mapping[str, Any]]]:
        st = self.store
        try:
            lo, hi = P.open_window(st, day)
            clo, chi = P.close_window(st, day)
            nlo, nhi = P.news_window(st, day)
            dlo, dhi = P.day_news_window(st, day)
        except LookupError:
            return {f: [] for f in FAMILIES + FILE_FAMILIES}
        e8k = P.filings_in(st, "8-K", lo, hi, since=EPOCH)
        ern_close = [r for r in P.filings_in(st, "8-K", clo, chi, since=EPOCH) if P.ERN_ITEMS & P.items_of(r)]
        by_symbol = self.elig.symbols(day)
        news = [dict(a) | {"cik": by_symbol.get(a["symbol"])} for a in P.news_in(st, nlo, nhi, since=EPOCH)]
        day_news = [dict(a) | {"cik": by_symbol.get(a["symbol"])} for a in P.news_in(st, dlo, dhi, since=EPOCH)]
        return {"ern": e8k, "8k": e8k, "ins": P.ins_triggers(st, lo, hi, since=EPOCH),
                "ins-buy": P.ins_buys(st, lo, hi, since=EPOCH), "news": news, "ern-react": ern_close,
                "news-day": day_news, "news-react": day_news, **self._file_windows(day, by_symbol)}

    def _file_windows(self, day: dt.date, by_symbol: Mapping[str, str]) -> dict[str, list[Mapping[str, Any]]]:
        """PREREG-EVL-4'S AND -5'S ROWS OF ENTRY SESSION `day` (release 1019h; the module docstring): `close_rows_4` and
        `close_rows_5` over the same windows their close decision reads, with no registration floor, every price unread
        (TAKEN (a) and (c) and the <= 0.96 skip skip nothing; no issuer waits), TAKEN (b) from the stored PROMPT-NEWS
        verdicts, NO NEW INFORMATION (i) by the kept eligibility's tickers. {family: rows} for `FILE_FAMILIES`; a family
        whose windows the calendar cannot place has none."""
        st = self.store
        out: dict[str, list[Mapping[str, Any]]] = {f: [] for f in FILE_FAMILIES}
        try:
            clo, chi = P.close_window(st, day)
            dlo, dhi = P.day_news_window(st, day)
            nlo, nhi = P.news_window(st, day)
        except LookupError:
            return out

        def with_cik(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
            return [dict(a) | {"cik": by_symbol.get(a["symbol"])} for a in rows]

        def symbol_of(cik: str) -> str | None:
            row = self.elig.row(day, cik)
            return None if row is None else str(row["symbol"])
        all8k = P.filings_window(st, "8-K", clo, chi)
        day_all = with_cik(P.news_rows(st, dlo, dhi))
        out.update(P.close_rows_4(all8k, day_all, with_cik(P.news_rows(st, nlo, nhi)), symbol_of))
        ern = [r for r in all8k if r.get("cik") and P.items_of(r) & P.ERN_ITEMS]
        taken, _ = P.taken_close_5(ern, day_all, symbol_of=symbol_of, reaction=lambda row: None,
                                   day_reaction=lambda cik: None, news_answer=self._news_answer)
        night2: list[Mapping[str, Any]] = []
        try:
            windows = P.night2_windows(st, day)
            attention = with_cik(P.news_rows(st, *P.attention_window(st, day)))
        except LookupError:
            attention = []
        if attention:
            tickers = {symbol: {cik} for symbol, cik in by_symbol.items()}
            named = P.named_ciks(P.news_named(st, *windows["named"]), tickers)
            filed = P.filed_ciks(P.filings_window(st, "8-K", *windows["filed"]))
            bought = P.bought_ciks(P.ins_buys_window(st, *windows["bought"]))
            night2 = P.no_new_info(attention, named, filed, bought, symbol_of)
        out.update(P.close_rows_5(ern, night2, taken=taken, waiting=set(), dropped=set()))
        return out

    def _news_answer(self, article: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """TAKEN (b)'s reading of a DAY(D) article: its stored PROMPT-NEWS verdict when `ok` ({status, score}), else None
        (none stored, `unparsed` or `refused`: never taken by it)."""
        got = self.scores.get(f"news|news:{article.get('id')}")
        return None if got is None else {"status": "ok", "score": got[0]}

    def _verdict(self, row: Mapping[str, Any]) -> int | None:
        key = f"doc|8k:{row['accession']}" if row.get("accession") else f"news|news:{row.get('id')}"
        got = self.scores.get(key)
        return None if got is None else got[0]

    def _guidance(self, row: Mapping[str, Any]) -> str | None:
        got = self.scores.get(f"doc|8k:{row['accession']}") if row.get("accession") else None
        return None if got is None else got[1]

    def selected(self, prog: P.Program) -> dict[dt.date, list[str]]:
        """{session: the events `prog`'s rule selects in it} over the facts' sessions: the lane's own `select` with its
        registration time set aside, one event an issuer a decision (the earliest knowable, as `write_intents`), the
        reaction unread (`unread_reaction`; PREREG-EVL-5's earnings rows `facts_reaction`, release 1019h) and the gap
        unread (`unread_gap`)."""
        key = f"{prog.id}|{prog.spec or ''}"     # (a PREREG program's version 2 selects as its version 1)
        if key in self._selected:
            return self._selected[key]
        unbounded = dataclasses.replace(prog, born_at=S.iso(EPOCH))
        out: dict[dt.date, list[str]] = {}
        with outcome_free(self.store.db):
            for day in self.days:
                rows = self.rows[day].get(prog.family, [])
                got = P.select(unbounded, rows, eligible=lambda cik, day=day: self.elig.row(day, cik),
                               verdict=self._verdict, reaction=facts_reaction(prog), guidance=self._guidance,
                               gap=unread_gap)
                taken: set[str] = set()
                events = []
                for c in sorted(got, key=lambda c: (c.knowable_at, c.event)):
                    if c.cik in taken:
                        continue
                    taken.add(c.cik)
                    events.append(c.event)
                out[day] = events
        self._selected[key] = out
        return out

    def count(self, prog: P.Program) -> int:
        return sum(len(v) for v in self.selected(prog).values())

    def candidates(self, specs: Iterable[Any]) -> dict[str, dict[str, Any]]:
        """PER-CANDIDATE SELECTION COUNTS (outcome-free): {id: {selected, per_session, by_session (one count a session,
        oldest first), upper_bound (a react family: the reaction is never read)}} of each spec the grammar parses, or
        {id or "?": {refused: reasons}}."""
        out: dict[str, dict[str, Any]] = {}
        for raw in specs:
            try:
                sp = parse(raw)
            except SpecError as exc:
                ident = raw.get("id") if isinstance(raw, Mapping) and isinstance(raw.get("id"), str) else "?"
                out[ident] = {"refused": exc.reasons}
                continue
            by = self.selected(program(sp, born_at=S.iso(EPOCH)))
            total = sum(len(v) for v in by.values())
            rated = sum(len(by[d]) for d in self.recorded)
            out[sp["id"]] = {"selected": total, "per_session": round(total / len(self.days), 2) if self.days else 0.0,
                             "by_session": [len(by[d]) for d in self.days],
                             "per_recorded_session": round(rated / len(self.recorded), 2) if self.recorded else 0.0,
                             "upper_bound": sp["family"] in REACT_FAMILIES}
            named = renamed(raw)
            if named is not None:
                out[sp["id"]]["named_from"] = named["from"]
        return out

    def facts(self, programs: Sequence[P.Program] | None = None) -> dict[str, Any]:
        """The architect's facts (JSON-ready; counts only): the module docstring's list."""
        progs = list(P.PROGRAMS if programs is None else programs)
        n = len(self.days)
        fam: dict[str, dict[str, Any]] = {}
        items: dict[str, int] = {}
        sources: dict[str, int] = {}
        hours: dict[str, dict[str, int]] = {"8k": {}, "news": {}, "news-day": {}}
        scores: dict[str, dict[str, int]] = {}
        guidance: dict[str, int] = {}
        values = {"50k-100k": 0, "100k-250k": 0, "250k-1m": 0, "1m+": 0}
        roles = {"director": 0, "officer": 0, "both": 0}
        seen: set[tuple[str, str]] = set()
        forms: dict[str, set[str]] = {"8-K": set(), "4": set()}
        with outcome_free(self.store.db):
            for day in self.days:
                for family in ("ern", "ern-react", "ins", "ins-buy"):
                    for row in self.rows[day].get(family, []):
                        forms["8-K" if family.startswith("ern") else "4"].add(str(row.get("accession")))
                for row in self.rows[day].get("8k", []):
                    forms["8-K"].add(str(row.get("accession")))
            recorded = set(self.recorded)
            on_recorded: dict[str, int] = {}
            for day in self.days:
                for family in FAMILIES:     # (the grammar's families: PREREG-EVL-4's and -5's rows are counted by program)
                    rows = self.rows[day].get(family, [])
                    slot = fam.setdefault(family, {"events": 0, "eligible": 0})
                    for row in rows:
                        items_ = P.items_of(row) if row.get("accession") and family in ("ern", "8k", "ern-react") else set()
                        if family == "ern" and not items_ & P.ERN_ITEMS:
                            continue
                        if family == "8k" and (items_ & P.ERN_ITEMS or not items_):
                            continue
                        slot["events"] += 1
                        uni = self.elig.row(day, row.get("cik"))
                        if uni is None or (family in NEWS_FAMILIES and uni["symbol"] != row.get("symbol")):
                            continue
                        slot["eligible"] += 1
                        if day in recorded:
                            on_recorded[family] = on_recorded.get(family, 0) + 1
                        ident = str(row.get("accession") or row.get("id"))
                        first = (family, ident) not in seen
                        seen.add((family, ident))
                        knowable_hour = str(S.parse_iso(row["knowable_at"]).astimezone(C.NY).hour)
                        if family == "8k" and first:
                            for item in sorted(items_):
                                items[item] = items.get(item, 0) + 1
                            hours["8k"][knowable_hour] = hours["8k"].get(knowable_hour, 0) + 1
                        if family in ("news", "news-day") and first:
                            src = str(row.get("source") or "").strip().lower() or "(none)"
                            sources[src] = sources.get(src, 0) + 1
                            hours[family][knowable_hour] = hours[family].get(knowable_hour, 0) + 1
                        if family in ("ern", "8k", "news", "news-day", "ern-react") and first:
                            v = self._verdict(row)
                            if v is not None:
                                book = scores.setdefault(family, {})
                                book[str(v)] = book.get(str(v), 0) + 1
                            if family == "ern":
                                g = self._guidance(row)
                                if g is not None:
                                    guidance[g] = guidance.get(g, 0) + 1
                        if family == "ins-buy" and first:
                            value = float(row.get("purchase_value") or 0.0)
                            band = "50k-100k" if value < 100_000 else "100k-250k" if value < 250_000 else \
                                "250k-1m" if value < 1_000_000 else "1m+"
                            values[band] += 1
                            d, o = bool(row.get("by_director")), bool(row.get("by_officer"))
                            roles["both" if d and o else "director" if d else "officer"] += 1
            k = len(self.recorded)
            for family, slot in fam.items():
                slot["per_session"] = round(slot["eligible"] / n, 2) if n else 0.0
                slot["per_recorded_session"] = round(on_recorded.get(family, 0) / k, 2) if k else 0.0
            covered_items: set[str] = set(P.OTHER_ITEMS)
            for p in progs:
                if p.spec is not None and p.family == "8k":
                    covered_items |= set(_spec_of(p.spec)["rule"].get("items") or [])
            listed: list[dict[str, Any]] = []
            done: set[tuple[str, str]] = set()
            for p in progs:
                ident = (p.id, p.spec or "")
                if ident in done:
                    continue     # (a PREREG program's version 2 selects as its version 1 does)
                done.add(ident)
                total = self.count(p)
                listed.append({"id": p.id, "family": p.family, "seatable": bool(p.can_seat or p.seatable),
                               "birth": p.spec is not None, "selected": total,
                               "per_session": round(total / n, 2) if n else 0.0,
                               "per_recorded_session": self.rate(p)[1]})
        busy = {p.family for p in progs}
        return {
            "as_of": self.today.isoformat(), "sessions": n,
            "first": self.days[0].isoformat() if self.days else None,
            "last": self.days[-1].isoformat() if self.days else None,
            "recorded_sessions": len(self.recorded),
            "families": {f: fam.get(f, {"events": 0, "eligible": 0, "per_session": 0.0, "per_recorded_session": 0.0})
                         for f in FAMILIES},
            "forms": {"8-K": len(forms["8-K"]), "4-buys": len(forms["4"])},
            "items_8k": dict(sorted(items.items())),
            "news_sources": dict(sorted(sources.items(), key=lambda kv: (-kv[1], kv[0]))[:15]),
            "hours": {k: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for k, v in hours.items()},
            "scores": {k: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for k, v in sorted(scores.items())},
            "guidance_ern": dict(sorted(guidance.items())),
            "ins_buy": {"value": values, "roles": roles},
            "programs": listed,
            "unprogrammed": {"families": [f for f in FAMILIES if f not in busy],
                             "items_8k": sorted(i for i in items if i not in covered_items)},
            "react_counts": "upper bounds: a reaction is a price after the event, never read here (so the rate floor "
                            "barely binds a react rule)",
        }


def jaccard(a: set[str], b: set[str]) -> float:
    """|a & b| / |a | b|; 0 when either is empty (a rule that selects nothing is the rate's to refuse, no duplicate)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _events(selected: Mapping[dt.date, Sequence[str]]) -> set[str]:
    return {e for events in selected.values() for e in events}


# ----------------------------------------------------------------------------------------------------------- the budget
def budget_used_hundredths(store: Any) -> int:
    """Hundredths of an expected false pass already charged (PREREG-EVL-6 section 5): the screen's own count
    (league/events/screen.py `budget6`, after `load_births`: 0.13 for every PREREG-EVL-6 version in SEATING, its fifteen
    new versions and every seatable birth's, retired ones included, any later version of a seatable id the store has
    seen, and every fresh run started). Never a figure written here."""
    return int(SN.budget6(store)["used"])


def budget_waiting_hundredths(store: Any) -> int:
    """What the runs waiting for the lane's budget would charge (0.13 each, league/events/screen.py `waiting_runs`):
    PREREG-EVL-6 section 3, a birth registers only when the room left after every waiting run holds its charge."""
    return CHARGE_HUNDREDTHS * len(SN.waiting_runs(store))


def budget_reserved_hundredths() -> int:
    """What the frozen files whose code is not live hold from the births' room (`RESERVED`, A137)."""
    return sum(int(h) for _, pin, h in RESERVED if getattr(P, pin, None) is None)


def budget_used_tenths(store: Any) -> int:
    """(Release 1019h's name: the charges in tenths, rounded up, for its readers. The validator reads
    `budget_used_hundredths`.)"""
    return -(-budget_used_hundredths(store) // 10)


def _tonight(store: Any, night: dt.date | None) -> int:
    """The seatable births already registered for `night` (a second run of the night, the captain's beside the
    architect's, shares its three)."""
    if night is None or "births" not in _tables(store.db):
        return 0
    return int(store.db.execute("SELECT COUNT(*) FROM births WHERE night=? AND seatable=1",
                                (night.isoformat(),)).fetchone()[0])


def budget(store: Any, night: dt.date | None = None) -> dict[str, Any]:
    """The stated budget as it stands: tenths used (every seatable version ever registered), the limit, what is left,
    and the seatable births `night` may still register."""
    used = budget_used_hundredths(store)
    waiting = budget_waiting_hundredths(store)
    reserved = budget_reserved_hundredths()
    tonight = _tonight(store, night)
    room = BUDGET_HUNDREDTHS - used - waiting - reserved
    return {"used": used / 100, "limit": BUDGET_HUNDREDTHS / 100, "left": (BUDGET_HUNDREDTHS - used) / 100,
            "waiting_runs": waiting / 100, "reserved": reserved / 100, "left_for_births": room / 100,
            "seatable_left_tonight": max(0, min(SEATABLE_A_NIGHT - tonight, room // CHARGE_HUNDREDTHS)),
            "charge": CHARGE_HUNDREDTHS / 100}


# ----------------------------------------------------------------------------------------------------------- validator
def _why(text: Any) -> str:
    line = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    return line[:WHY_MAX]


def validate(store: Any, facts: Facts, proposals: Sequence[Mapping[str, Any]], *,
             night: dt.date | None = None) -> list[dict[str, Any]]:
    """THE VALIDATOR (the module docstring), in order: each proposal {spec, why, by} gets {seq, id, sha, spec (canonical,
    or the raw text when the grammar refused it), why, by, ok, reasons, selected, per_session, jaccard (the highest, and
    with whom), charge (tenths), named ({from, to}: the proposed id and the House's name of it, A95, or None)}; an
    accepted seatable birth is charged before the next is judged. `store` must have its births loaded
    (programs.load_births) so the registered ids and the budget are current."""
    known_ids = {p.id for p in P.PROGRAMS}
    known_sha: set[str] = set()
    if "births" in _tables(store.db):
        for r in store.db.execute("SELECT id, sha FROM births"):
            known_ids.add(str(r["id"]))
            known_ids.add(control_id(str(r["id"])))
            known_sha.add(str(r["sha"]))
    used = budget_used_hundredths(store) + budget_waiting_hundredths(store) + budget_reserved_hundredths()
    # (the waiting runs come first: section 3; then the frozen files' reservations, A137)
    tonight_used = _tonight(store, night)
    registered = [(p.id, _events(facts.selected(p))) for p in P.PROGRAMS]
    accepted: list[tuple[str, set[str]]] = []
    out: list[dict[str, Any]] = []
    for seq, proposal in enumerate(proposals):
        raw = proposal.get("spec") if isinstance(proposal, Mapping) else None
        entry: dict[str, Any] = {"seq": seq, "id": None, "sha": None, "why": _why((proposal or {}).get("why")),
                                 "by": _why((proposal or {}).get("by")) or "architect", "ok": False, "reasons": [],
                                 "selected": None, "per_session": None, "jaccard": None, "charge": 0,
                                 "named": renamed(raw)}
        try:
            spec = parse(raw)
        except SpecError as exc:
            entry["spec"] = json.dumps(raw, sort_keys=True, default=str)[:4000]
            entry["reasons"] = exc.reasons
            out.append(entry)
            continue
        text = canonical(spec)
        digest = hashlib.sha256(text.encode("ascii")).hexdigest()
        entry |= {"spec": text, "id": spec["id"], "sha": digest}
        why: list[str] = []
        if spec["id"] in known_ids or control_id(spec["id"]) in known_ids:
            why.append(f"{spec['id']} is registered already (a change is a new birth with a new id)")
        if digest in known_sha:
            why.append("this very spec is registered already")
        prog = program(spec, born_at=S.iso(EPOCH))
        mine = _events(facts.selected(prog))
        entry["selected"] = len(mine)
        bound = " (an upper bound: the reaction is never read)" if spec["family"] in REACT_FAMILIES else ""
        if spec["seatable"]:
            # SUP-3 (A97, release 1019h): MIN_RATE a session over the window's sessions holding a complete record pass.
            rated, rate = facts.rate(prog)
            entry["per_session"] = rate
            if not facts.rated:
                why.append(f"{len(facts.recorded)} of the last {SESSIONS} sessions hold a complete record pass, under "
                           f"the {MIN_RECORDED} a seatable birth's rate is read over")
            elif rated < MIN_RATE * len(facts.recorded):
                why.append(f"{rated} selected events over the {len(facts.recorded)} sessions of the last {SESSIONS} "
                           f"with a complete record pass: under {MIN_RATE} a session" + bound)
        else:
            entry["per_session"] = round(len(mine) / len(facts.days), 2) if facts.days else 0.0
            if not facts.complete:
                why.append(f"the store holds {len(facts.days)} sessions, not the {SESSIONS} the rate is read over")
            elif len(mine) < RECORD_MIN_RATE * SESSIONS:
                why.append(f"{len(mine)} selected events over the last {SESSIONS} sessions: under {RECORD_MIN_RATE} a "
                           "session" + bound)
        worst = (0.0, None)
        for other, events in registered + accepted:
            j = jaccard(mine, events)
            if j > worst[0] or worst[1] is None:
                worst = (j, other)
        entry["jaccard"] = {"max": round(worst[0], 4), "with": worst[1]}
        if worst[1] is not None and worst[0] >= JACCARD_MAX:
            why.append(f"a duplicate of {worst[1]}: Jaccard {worst[0]:.2f} >= {JACCARD_MAX} over the last {SESSIONS} "
                       "sessions' selected events")
        if spec["seatable"] and not why:
            if tonight_used + 1 > SEATABLE_A_NIGHT:
                why.append(f"{SEATABLE_A_NIGHT} seatable births a night at most")
            elif used + CHARGE_HUNDREDTHS > BUDGET_HUNDREDTHS:
                why.append(f"the false-pass budget: {used / 100:.2f} of {BUDGET_HUNDREDTHS / 100:.2f} used or held for "
                           f"the runs waiting for it, a seatable birth adds {CHARGE_HUNDREDTHS / 100:.2f} "
                           "(PREREG-EVL-6 section 5)" + (f"; {budget_reserved_hundredths() / 100:.2f} of it held for the "
                           "frozen files whose code is not live (A137)" if budget_reserved_hundredths() else ""))
        if why:
            entry["reasons"] = why
            out.append(entry)
            continue
        entry["ok"] = True
        if spec["seatable"]:
            entry["charge"] = CHARGE_HUNDREDTHS
            used += CHARGE_HUNDREDTHS
            tonight_used += 1
        known_ids |= {spec["id"], control_id(spec["id"])}
        known_sha.add(digest)
        accepted.append((spec["id"], mine))
        out.append(entry)
    return out


# ----------------------------------------------------------------------------------------------------------- proposer
SYSTEM = ("You are the architect of LTCM's event lane. You design pre-registered rules over public US-stock events "
          "(SEC 8-K filings, Form 4 insider buys, single-company news) that buy whole shares long-only and hold them "
          "for a session. You see only outcome-free facts: event counts and the stored verdicts of a fixed reading "
          "prompt. You never see a price after an event, a return, a profit or a test result. Answer with JSON only.")

#: TWO VALID SPECS the prompt shows (A95: the first night's six were all refused by the grammar): an 8k spec over items
#: outside READ_ITEMS_8K with no score or guidance field, and a news spec. The form only; each parses (a test holds it).
EXAMPLES: tuple[dict[str, Any], ...] = (
    {"id": "EVL-B-8K-OFFICERS-O1", "version": 1, "family": "8k", "rule": {"items": ["5.02"]}, "entry": "open",
     "exit": "close", "hold": 1, "rank": "none", "seatable": True},
    {"id": "EVL-B-NEWS-PREMARKET-O1", "version": 1, "family": "news", "rule": {"score_min": 1, "hours": [6, 7, 8]},
     "entry": "open", "exit": "close", "hold": 1, "rank": "score", "seatable": True},
)

USER = """THE GRAMMAR. A spec is a JSON object with exactly these fields:
- "id": "EVL-B-" then upper-case letters/digits groups joined by "-" (at most 40 characters), new. Every id starts
  with EVL-B-.
- "version": 1.
- "family": one of ern (8-K item 2.02, buy at the next open), ern-react (8-K 2.02 knowable during the session, buy at
  the close after its reaction), 8k (8-Ks carrying one of an item set, never 2.02, next open), ins (Form 4 cluster of
  2+ insiders buying, next open), ins-buy (one director or officer buying >= $50,000 in the open market, next open),
  news (single-company articles overnight, next open), news-day (the day's articles to 15:29 ET, buy at the close),
  news-react (the day's articles with the stock's reaction, buy at the close).
- "rule": only these fields, by family:
  ern: score_min, score_max (integers -3..3: the stored verdict of the filing), guidance (a list of raised, maintained,
  lowered, none, unclear); ern-react: score_min, score_max, react_min (1.01..1.25) or react_max (0.75..0.99), the
  reaction being the 15:29 price over the last close before the event; 8k: items (a list of 8-K items such as 1.01,
  5.02, 8.01), and score_min, score_max, guidance only as the next line says; ins: value_min (dollars >= 50000);
  ins-buy: value_min (>= 50000), roles (one string, "director" or "officer"); news and news-day: score_min,
  score_max, sources (news source names), hours (New York hours 0..23 of the article); news-react: react_min or
  react_max, sources, hours.
- An 8k spec may carry score_min, score_max or guidance (or rank "score") only when every one of its items is among
  <<READ_ITEMS>>, and guidance is a list such as ["raised"], never an object; over any other item an 8k spec has
  items alone and rank "none".
- "entry": "open" for ern, 8k, ins, ins-buy, news; "close" for ern-react, news-day, news-react.
- "exit": "close" (the close of session h; the only exit after an open entry) or "open" (the next open, after a close
  entry).
- "hold": h, 1..5 sessions; 1 when seatable.
- "rank": "score", "reaction" (react families), "value" (Form 4) or "none".
- "seatable": true (trades real money at learning size from its first event and is judged by the screen) or false (a
  record, free). An ins (Form 4 cluster) spec must be seatable false: a record only.
TWO VALID SPECS (the form only; your rules come from the facts):
<<EXAMPLES>>
THE VALIDATOR refuses a seatable spec that selects fewer than <<MIN_RATE>> events a session over the sessions of the
last <<SESSIONS>> that hold a complete record pass ("recorded_sessions" in the facts, at least <<MIN_RECORDED>>; each
count's "per_recorded_session"), a record spec that selects fewer than <<RECORD_MIN_RATE>> a session over the last
<<SESSIONS>> sessions, and any spec whose selected events overlap any existing program's with a Jaccard of <<JACCARD>>
or more. Each seatable spec costs <<CHARGE>> of the false-pass budget: <<BUDGET>>. Propose at most <<K>> specs, at most
<<SEATABLE>> of them seatable. Prefer rules a reader could explain in one line, over events and items no program covers
yet. Propose no spec of an earnings-only family (ern, ern-react) after Nov 6, 2026 (the facts' "as_of"): the earnings
season ends and such a rule would not fill its slots.

THE FACTS (counts over the last <<SESSIONS>> sessions; "eligible" are the events of listed, liquid operating
companies the lane can trade; react counts are upper bounds, so the rate floor barely binds a react rule):
<<FACTS>>

Answer with JSON only: {"specs": [{"spec": {...}, "why": "one line"}]}""".replace(
    "<<EXAMPLES>>", "\n".join(json.dumps(x, separators=(", ", ": ")) for x in EXAMPLES))


def prompt_sha() -> str:
    """The proposer's prompt version: model, temperature, effort, max_tokens, the system text and the user template."""
    spec = {"model": MODEL, "temperature": TEMPERATURE, "effort": EFFORT, "max_tokens": MAX_TOKENS, "system": SYSTEM,
            "user": USER}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()


def render(facts: Mapping[str, Any], budget_: Mapping[str, Any], *, k: int = K) -> str:
    text = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    left = int(budget_.get("seatable_left_tonight", 0))
    return (USER.replace("<<READ_ITEMS>>", ", ".join(READ_ITEMS_8K)).replace("<<MIN_RATE>>", str(MIN_RATE))
            .replace("<<MIN_RECORDED>>", str(MIN_RECORDED)).replace("<<RECORD_MIN_RATE>>", str(RECORD_MIN_RATE))
            .replace("<<SESSIONS>>", str(SESSIONS)).replace("<<JACCARD>>", str(JACCARD_MAX))
            .replace("<<BUDGET>>", f"{budget_['used']:.2f} of {budget_['limit']:.2f} used")
            .replace("<<CHARGE>>", f"{float(budget_.get('charge', CHARGE_HUNDREDTHS / 100)):.2f}")
            .replace("<<K>>", str(k)).replace("<<SEATABLE>>", str(left)).replace("<<FACTS>>", text))


def request_body(user_text: str) -> dict[str, Any]:
    """The architect's request (`propose`): the model, `max_tokens`, its effort, the system text and the rendered user
    text, streamed with its thinking summarized (`STREAM`, `THINKING`); a temperature only when `TEMPERATURE` is not None
    (Opus 5.5 has no sampling parameter)."""
    body: dict[str, Any] = {"model": MODEL, "max_tokens": MAX_TOKENS, "output_config": {"effort": EFFORT},
                            "system": SYSTEM, "messages": [{"role": "user", "content": user_text}]}
    if STREAM:
        body["stream"] = True
        body["thinking"] = dict(THINKING)
    if TEMPERATURE is not None:
        body["temperature"] = TEMPERATURE
    return body


def worst_usd(user_text: str) -> float:
    """The call's worst case: its input at a token every CHARS_A_TOKEN characters and its whole max_tokens out."""
    tokens_in = math.ceil((len(SYSTEM) + len(user_text)) / CHARS_A_TOKEN)
    return tokens_in * PRICE_IN + MAX_TOKENS * PRICE_OUT


def spent(store: Any, night: dt.date) -> float:
    row = store.db.execute("SELECT COALESCE(SUM(usd), 0) FROM birth_calls WHERE night=?", (night.isoformat(),)).fetchone()
    return float(row[0] or 0.0)


def parse_answer(text: str, *, k: int = K) -> tuple[list[dict[str, Any]], int]:
    """([{spec, why}] the first `k` of the answer's specs, how many it held), from {"specs": [...]} or a bare list
    (a fenced block is read as its content). Anything else: ([], 0)."""
    body = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.S)
    if fence:
        body = fence.group(1)
    try:
        data = json.loads(body)
    except ValueError:
        return [], 0
    items = data.get("specs") if isinstance(data, Mapping) else data
    if not isinstance(items, list):
        return [], 0
    out = []
    for item in items[: max(0, int(k))]:
        if isinstance(item, Mapping) and "spec" in item:
            out.append({"spec": item.get("spec"), "why": item.get("why"), "by": f"architect:{MODEL}"})
        else:
            out.append({"spec": item, "why": None, "by": f"architect:{MODEL}"})
    return out, len(items)


def _stated(gw: Any) -> float | None:
    """The gateway's cost of the answer just read (`X-LTCM-Cost-USD`), or None when it stated none or marked it unknown
    (`X-LTCM-Cost-Known: false`: the gateway could not read the usage)."""
    headers = getattr(gw, "last_headers", None) or {}
    if str(headers.get(G.COST_KNOWN_HEADER) or "").lower() == "false":
        return None
    try:
        usd = float(headers.get(V.COST_HEADER))
    except (TypeError, ValueError):
        return None
    return usd if usd == usd and 0.0 <= usd < float("inf") else None


def propose(store: Any, gw: Any, facts: Mapping[str, Any], *, night: dt.date, now: Callable[[], dt.datetime],
            k: int = K, cap: float = NIGHT_USD, line_left: float | None = None) -> dict[str, Any]:
    """THE ARCHITECT'S ONE CALL A NIGHT (the module docstring): {status, proposals, offered, usd, prompt_sha,
    facts_sha, seconds}. A night's stored answer is read again (never asked again). The call is streamed
    (`gw.post_stream`, within `CALL_LIMIT`; `STREAM`'s comment) and ends as one of `LOST`'s comment's statuses: an answer
    (`ok`, `cut`, `refused`) or a LOST call is stored with its cost (a lost one at the gateway's stated cost, else its
    worst case) and never asked again; a call that went out is never asked twice. `no answer` stores nothing: nothing was
    billed (the lane refused it, the gateway never had it, or the gateway settled its error at nothing). `line_left`
    (the House's lane, league/events/house.py `line_left`): what is left of the lane's line today; the call's worst case
    must fit under it too (release 1019e's review: the call is inside the lane's line), or no call is made."""
    psha = prompt_sha()
    facts_text = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    fsha = hashlib.sha256(facts_text.encode("utf-8")).hexdigest()
    have = store.db.execute("SELECT * FROM birth_calls WHERE night=? AND prompt_sha=? AND model=?",
                            (night.isoformat(), psha, MODEL)).fetchone()
    base = {"prompt_sha": psha, "facts_sha": fsha}
    if have is not None:
        props, offered = parse_answer(str(have["answer"] or ""), k=k) if have["status"] == "ok" else ([], 0)
        return base | {"status": f"stored:{have['status']}", "proposals": props, "offered": offered,
                       "usd": float(have["usd"] or 0.0), "facts_sha": have["facts_sha"] or fsha}
    user = render(facts, budget(store, night), k=k)
    worst = worst_usd(user)
    already = spent(store, night)
    if already + worst > cap:
        return base | {"status": "cap", "proposals": [], "offered": 0, "usd": 0.0,
                       "why": f"the call's worst case ${worst:.4f} over the night's ${cap - already:.4f} left"}
    if line_left is not None and worst > line_left:
        return base | {"status": "cap", "proposals": [], "offered": 0, "usd": 0.0,
                       "why": f"the call's worst case ${worst:.4f} over the ${max(0.0, line_left):.4f} left of the lane's "
                              "line today"}
    request_id = f"evl-births:{night.isoformat()}:{psha[:12]}"
    body = request_body(user)
    user_sha = hashlib.sha256(user.encode("utf-8")).hexdigest()
    asked = now()
    key = (night.isoformat(), psha, MODEL)
    # (release 1019h's re-review, fixed in release 1019i: THE ROW AHEAD OF THE CALL, `ASKED` at the call's worst case,
    # its answered_at the asking time so the day's spend counts it; the call's end is an UPDATE of it)
    with store.tx() as db:
        db.execute("INSERT OR IGNORE INTO birth_calls(night, prompt_sha, model, request_id, asked_at, answered_at, "
                   "status, user_sha, facts_sha, answer, usd) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                   (*key, request_id, S.iso(asked), S.iso(asked), ASKED, user_sha, fsha, worst))

    def store_row(status: str, text: str | None, usd: float) -> dict[str, Any]:
        answered = now()
        with store.tx() as db:
            db.execute("UPDATE birth_calls SET answered_at=?, status=?, answer=?, usd=? WHERE night=? AND prompt_sha=? "
                       "AND model=?", (S.iso(answered), status, text, usd, *key))
        return {"usd": usd, "seconds": round(max(0.0, (answered - asked).total_seconds()), 3)}

    def drop_row() -> None:
        """A call that never went out (the lane refused it, or the gateway never had it): nothing was billed."""
        with store.tx() as db:
            db.execute("DELETE FROM birth_calls WHERE night=? AND prompt_sha=? AND model=? AND status=?", (*key, ASKED))

    billed = 0.0            # what the gateway settled for errors that carried no answer (a 429 or a 5xx it settled)
    last = "no call"
    try:
        for _ in range(2):
            try:
                code, payload = gw.post_stream(V.PATH, body, headers={V.REQUEST_HEADER: request_id}, limit=CALL_LIMIT,
                                               gap=STREAM_GAP)
            except G.NotSent as exc:            # (the lane refused it: it never went out)
                last = f"{type(exc).__name__}: {str(exc)[:120]}"
                break
            except urllib.error.URLError as exc:   # (sending failed: the gateway never had the whole request)
                last = f"{type(exc).__name__}: {str(exc)[:120]}"
                continue
            except OSError as exc:              # (it went out: lost while waiting for the answer, or its stream lost)
                last = f"{type(exc).__name__}: {str(exc)[:120]}"
                told = exc.cost if isinstance(exc, G.StreamLost) and exc.known else None
                kept = store_row(LOST, None, billed + (worst if told is None else told))
                return base | {"status": LOST, "proposals": [], "offered": 0, "why": last} | kept
            stated = _stated(gw)
            if not 200 <= code < 300:
                last = f"HTTP {code}"
                refusal = isinstance(payload, Mapping) and payload.get("cap") is not None   # (the gateway's own, unsent)
                if stated is None and code >= 500 and not refusal:
                    # (a 5xx the gateway did not settle: the call may have gone out and run; unknown is not free)
                    kept = store_row(LOST, None, billed + worst)
                    return base | {"status": LOST, "proposals": [], "offered": 0, "why": last} | kept
                billed += stated or 0.0
                if 400 <= code < 500 and code != 429:
                    break
                if already + billed + worst > cap or (line_left is not None and billed + worst > line_left):
                    last += f" (no second ask: ${billed:.4f} settled and the worst case ${worst:.4f} over what is left)"
                    break       # (asked again only inside the night's cap and the lane's line, the first ask counted)
                continue
            if not isinstance(payload, Mapping):
                last = f"HTTP {code}: no answer read"
                kept = store_row(LOST, None, billed + (worst if stated is None else stated))
                return base | {"status": LOST, "proposals": [], "offered": 0, "why": last} | kept
            text = "".join(b.get("text") or "" for b in payload.get("content") or []
                           if isinstance(b, Mapping) and b.get("type") == "text")
            stop = payload.get("stop_reason")
            status = "refused" if stop == "refusal" else "cut" if stop == "max_tokens" else "ok"
            kept = store_row(status, text, billed + (worst if stated is None else stated))   # (no stated cost: the worst)
            props, offered = parse_answer(text, k=k) if status == "ok" else ([], 0)
            return base | {"status": status, "proposals": props, "offered": offered} | kept
    except Exception as exc:  # noqa: BLE001 - release 1019i: ANY failure after the send is a LOST call at its worst
        last = f"{type(exc).__name__}: {str(exc)[:120]}"
        kept = store_row(LOST, None, billed + worst)
        return base | {"status": LOST, "proposals": [], "offered": 0, "why": last} | kept
    if billed > 0:
        kept = store_row(LOST, None, billed)
        return base | {"status": LOST, "proposals": [], "offered": 0, "why": last} | kept
    drop_row()
    return base | {"status": "no answer", "proposals": [], "offered": 0, "usd": 0.0, "why": last}


# ----------------------------------------------------------------------------------------------------------- register
def path_of(night: dt.date) -> str:
    return f"{DOCS_DIR}/{night.isoformat()}.jsonl"


def line_of(entry: Mapping[str, Any], *, night: dt.date, facts_sha: str | None, prompt: str | None) -> str:
    """The registered line: one JSON object (canonical: keys sorted, no spaces) carrying the canonical spec, its sha,
    the one-line rationale, who proposed it, the night, the facts' sha and the prompt's sha."""
    data = {"grammar": GRAMMAR, "spec": json.loads(entry["spec"]), "sha": entry["sha"], "why": entry.get("why") or "",
            "by": entry.get("by") or "architect", "night": night.isoformat(), "facts_sha": facts_sha,
            "prompt_sha": prompt}
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def register(store: Any, gw: Any, entries: Sequence[Mapping[str, Any]], *, night: dt.date,
             now: Callable[[], dt.datetime]) -> dict[str, Any]:
    """Append the accepted entries' lines (`line`) to docs/births/<night>.jsonl through the gateway's docs route; with
    GitHub's receipt, write each as a REGISTERED birth (`births`) at the later of GitHub's commit time and the House's
    receipt of the answer. {status: registered | unchanged | refused | unknown, ...}: `unknown` (no answer, or an answer
    without GitHub's commit time) is posted again by `reconcile`; `refused` was GitHub's or the gateway's no."""
    if not entries:
        return {"status": "nothing"}
    path = path_of(night)
    lines = [str(e["line"]) for e in entries]
    body = {"path": path, "lines": lines, "message": f"{len(lines)} birth(s) of {night.isoformat()}"}
    try:
        code, answer = gw.post_json(DOCS_ROUTE, body)
    except OSError as exc:
        return {"status": "unknown", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    received = now()
    answer = answer if isinstance(answer, Mapping) else {}
    if not 200 <= int(code) < 300 or answer.get("ok") is not True:
        unknown = int(code) >= 500 or int(code) == 429 or answer.get("refused") == "no_answer"
        return {"status": "unknown" if unknown else "refused", "code": int(code),
                "error": str(answer.get("error") or "")[:200], "refused": answer.get("refused")}
    committed = answer.get("committed_at")
    try:
        at = S.parse_iso(str(committed))
    except (TypeError, ValueError):
        return {"status": "unknown", "error": "the answer carries no GitHub commit time", "code": int(code)}
    registered_at = max(at, received)
    commit = str(answer.get("commit") or "")[:64] or None
    with store.tx() as db:
        for seq, e in enumerate(entries):
            spec = json.loads(str(e["spec"]))
            db.execute("INSERT OR IGNORE INTO births(id, version, sha, spec, seatable, registered_at, committed_at, "
                       "received_at, path, commit_sha, seq, line, why, by, night) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                       "?, ?, ?, ?, ?)",
                       (spec["id"], int(spec["version"]), e["sha"], e["spec"], int(bool(spec["seatable"])),
                        S.iso(registered_at), S.iso(at), S.iso(received), path, commit, seq, e["line"],
                        e.get("why") or "", e.get("by") or "", night.isoformat()))
    return {"status": "unchanged" if answer.get("committed") is False else "registered", "commit": commit,
            "committed_at": S.iso(at), "received_at": S.iso(received), "registered_at": S.iso(registered_at),
            "path": path, "lines": len(lines)}


def _set_status(store: Any, night: str, seqs: Iterable[int], status: str) -> None:
    with store.tx() as db:
        for seq in seqs:
            db.execute("UPDATE birth_candidates SET status=? WHERE night=? AND seq=?", (status, night, int(seq)))


def reconcile(store: Any, gw: Any, *, now: Callable[[], dt.datetime]) -> list[dict[str, Any]]:
    """Every night whose registration got no answer (`unknown`) posted again with the very same lines; registered when
    the route commits them now or answers that they stand already (its latest commit's time: later than the true one,
    the reading that counts fewer events)."""
    out = []
    nights = [str(r[0]) for r in store.db.execute("SELECT DISTINCT night FROM birth_candidates WHERE status='unknown' "
                                                  "ORDER BY night")]
    for night in nights:
        rows = [dict(r) for r in store.db.execute("SELECT * FROM birth_candidates WHERE night=? AND status='unknown' "
                                                  "ORDER BY seq", (night,))]
        entries = [{"spec": r["spec"], "sha": r["sha"], "line": r["line"], "why": r["why"], "by": r["by"]} for r in rows]
        got = register(store, gw, entries, night=dt.date.fromisoformat(night), now=now)
        if got["status"] in ("registered", "unchanged"):
            _set_status(store, night, [r["seq"] for r in rows], "registered")
        elif got["status"] == "refused":
            _set_status(store, night, [r["seq"] for r in rows], "refused")
        out.append({"night": night} | got)
    return out


# ----------------------------------------------------------------------------------------------------------- the night
def night(store: Any, gw: Any, *, today: dt.date, now: Callable[[], dt.datetime],
          proposals: Sequence[Mapping[str, Any]] | None = None, k: int = K, cap: float = NIGHT_USD,
          dry_run: bool = False, line_left: float | None = None,
          rerun: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE BIRTHS JOB of the night of `today` (receipt `births`): the unknown registrations of earlier nights posted
    again; the outcome-free facts; the architect's one call (or `proposals`, the captain's own {spec, why}: no call),
    held to the night's cap and to `line_left` (`propose`); the validator; the accepted lines registered (`dry_run`:
    validated and recorded, never registered); the births loaded again. Returns its summary. A night whose call ended
    without an answer (`UNANSWERED`: no answer, lost, cut, refused) finishes its receipt `unanswered`, its call's
    status, cost and seconds in the summary (release 1019h's fix round: the House warns, the report lists it). The
    receipt records the running `PARSE_VERSION` and, for the House's one re-run of an empty night (`rerun`,
    `rerun_due`'s answer), what it re-runs; both are written when the receipt starts, so a re-run that dies before it
    finishes is still the night's one re-run. A proposed id the House renamed is kept on its candidate row
    (`figures.named`: {from, to}) and in the receipt (`named`: {the House's name: the proposed id})."""
    P.load_births(store)
    rid = store.start_receipt(JOB, now=now())
    out: dict[str, Any] = {"night": today.isoformat(), "parse_version": PARSE_VERSION}
    if rerun is not None:
        out["rerun"] = dict(rerun)
    status = "ok"
    try:
        store.db.execute("UPDATE receipts SET summary=? WHERE id=?", (json.dumps(out, sort_keys=True, default=str), rid))
        facts = Facts(store, today)
        sheet = facts.facts()
        fsha = hashlib.sha256(json.dumps(sheet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        call = None
        if proposals is None:
            call = propose(store, gw, sheet, night=today, now=now, k=k, cap=cap, line_left=line_left)
            proposals = call["proposals"]
            out["call"] = {key: call.get(key) for key in ("status", "offered", "usd", "why", "prompt_sha", "seconds")}
            psha = call.get("prompt_sha")
            # (release 1019i: a night's STORED call that ended without an answer, `stored:lost` or `stored:asked`,
            # is unanswered too, as the call itself was)
            if str(call.get("status") or "").removeprefix("stored:") in UNANSWERED:
                status = "unanswered"     # (`LOST`'s comment: the House warns, the report lists it)
        else:
            proposals = [dict(p) | {"by": (p.get("by") or "captain")} for p in proposals]
            psha = None
        if not dry_run:
            # (release 1019h's re-review, fixed in release 1019i: the earlier nights' unknown registrations are posted
            # again AFTER the architect's call, so their network reads never eat the call's room inside the job's bound;
            # the births loaded again before the validator reads the registered ids and the budget)
            out["reconciled"] = reconcile(store, gw, now=now)
            P.load_births(store)
        checked = validate(store, facts, proposals, night=today)
        out["counts"] = {c["id"] or f"#{c['seq']}": {"selected": c["selected"], "per_session": c["per_session"],
                                                      "jaccard": c["jaccard"]} for c in checked}
        first = int(store.db.execute("SELECT COALESCE(MAX(seq) + 1, 0) FROM birth_candidates WHERE night=?",
                                     (today.isoformat(),)).fetchone()[0])
        for c in checked:
            c["seq"] = first + int(c["seq"])
            c["line"] = line_of(c, night=today, facts_sha=fsha, prompt=psha) if c["ok"] else None
        with store.tx() as db:
            for c in checked:
                figures = {"selected": c["selected"], "per_session": c["per_session"], "jaccard": c["jaccard"],
                           "charge": c["charge"]} | ({"named": c["named"]} if c.get("named") else {})
                db.execute("INSERT INTO birth_candidates(night, seq, sha, id, spec, why, by, status, reasons, figures, line, "
                           "at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (today.isoformat(), c["seq"], c["sha"], c["id"], c["spec"], c["why"], c["by"],
                            "accepted" if c["ok"] else "refused", json.dumps(c["reasons"]),
                            json.dumps(figures, sort_keys=True), c["line"], S.iso(now())))
        accepted = [c for c in checked if c["ok"]]
        out["proposed"] = len(checked)
        out["accepted"] = [c["id"] for c in accepted]
        out["refused"] = [{"id": c["id"], "why": c["reasons"][:3]} for c in checked if not c["ok"]][:K * 2]
        named = {c["named"]["to"]: c["named"]["from"] for c in checked if c.get("named")}
        if named:
            out["named"] = named
        if accepted and not dry_run:
            # (`unknown` first: a job that dies between GitHub's commit and the births rows is posted again next night)
            _set_status(store, today.isoformat(), [c["seq"] for c in accepted], "unknown")
            reg = register(store, gw, accepted, night=today, now=now)
            out["registration"] = reg
            final = {"registered": "registered", "unchanged": "registered", "refused": "refused",
                     "unknown": "unknown"}.get(reg["status"], "refused")
            _set_status(store, today.isoformat(), [c["seq"] for c in accepted], final)
            if final != "registered":
                status = "partial"
        P.load_births(store)
        out["budget"] = budget(store, today)
    except Exception as exc:  # noqa: BLE001 - the night's failure is its receipt's; the lane goes on
        status = "failed"
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    store.finish_receipt(rid, status, out, now=now())
    return out | {"_status": status}


def _version_of(summary_: Mapping[str, Any]) -> int:
    try:
        return int(summary_.get("parse_version") or PARSE_VERSION_BEFORE)
    except (TypeError, ValueError):
        return PARSE_VERSION_BEFORE


def rerun_due(store: Any, now: dt.datetime, *, version: int = PARSE_VERSION) -> dict[str, Any] | None:
    """THE ONE RE-RUN OF AN EMPTY NIGHT (A95, the captain's, 02:25Z Oct 22, 2026): the night whose births job the House
    runs once more NOW, as {night, of (its earlier receipts' ids), parse_version (theirs), until}, or None. The night is
    the latest one a births receipt names (receipts started within `RERUN_REACH`); it is due only when
    - every receipt of it was written by an OLDER reading than the running one (`parse_version` below `version`; a
      receipt of release 1019e records none: `PARSE_VERSION_BEFORE`), so the running parser and prompt have not read it;
    - no receipt of it is a re-run already (at most one re-run a night; a re-run that died running counts, since `night`
      writes its head when it starts);
    - it ACCEPTED NONE and REGISTERED NONE: no receipt names an accepted id, no candidate row of it is accepted,
      unknown or registered, and no birth is registered for it;
    - `now` is before `RERUN_BY` (12:55Z) of the session day after the night (no calendar row for it: never).
    WHY THE CUT-OFF IS SAFE EITHER WAY: a re-run birth counts only events knowable after its own registration (the later
    of GitHub's commit time and the House's receipt, `register`), like any birth, so whenever it lands no event the House
    saw before it is ever counted, and it is charged to the false-pass budget and the night's three like any. Started
    before 12:55Z it starts at least 5 minutes (65 in standard time) before the session's 09:00 ET cut-off and 20 (80)
    before its 09:15 ET open decision, so in the normal case (the night's first run took 11 s) it is registered before
    that session's first decision and its first session is whole. From 12:55Z it never starts: the session's
    decisions, sends and fills run from then to the close (the deploy-blocked window, which keeps the code fixed, keeps
    the program set fixed too), and a birth registered among them would begin its record part-way through a session it
    cannot fairly count; the night stays empty and the next session night's births job (21:15 ET, at the running
    reading) proposes again, so the only cost is that night's births. A night's re-run reuses its stored answer when the
    running prompt sha is the stored one (the parser changed, the prompt did not: no call), else makes the night's call
    inside `NIGHT_USD` (the night's first call counts in it) and the lane's line, as `propose` always does."""
    if "receipts" not in _tables(store.db):
        return None
    since = S.iso(now - RERUN_REACH)
    runs: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for r in store.db.execute("SELECT id, summary FROM receipts WHERE job=? AND started_at>=? AND summary IS NOT NULL "
                              "ORDER BY id", (JOB, since)):
        try:
            data = json.loads(str(r["summary"]))
            day = dt.date.fromisoformat(str(data.get("night")))
        except (TypeError, ValueError, AttributeError):
            continue
        runs.setdefault(day.isoformat(), []).append((int(r["id"]), data))
    if not runs:
        return None
    latest = max(runs)
    mine = runs[latest]
    if any(data.get("rerun") for _, data in mine):
        return None
    before = max(_version_of(data) for _, data in mine)
    if before >= version:
        return None
    if any(data.get("accepted") for _, data in mine):
        return None
    tables = _tables(store.db)
    if "births" in tables and store.db.execute("SELECT 1 FROM births WHERE night=? LIMIT 1", (latest,)).fetchone():
        return None
    if "birth_candidates" in tables and store.db.execute(
            "SELECT 1 FROM birth_candidates WHERE night=? AND status IN ('accepted', 'unknown', 'registered') LIMIT 1",
            (latest,)).fetchone():
        return None
    day = dt.date.fromisoformat(latest)
    after = C.sessions(store, day + dt.timedelta(days=1), day + RERUN_REACH)
    if not after:
        return None
    until = dt.datetime.combine(after[0].day, RERUN_BY, tzinfo=dt.timezone.utc)
    if now >= until:
        return None
    return {"night": latest, "of": [rid for rid, _ in mine], "parse_version": before, "until": S.iso(until)}


def summary(store: Any) -> dict[str, Any]:
    """The report's line: births registered (seatable, records), the last night's candidates and its model cost."""
    if "births" not in _tables(store.db):
        return {"registered": 0, "seatable": 0, "records": 0, "last_night": None}
    reg = store.db.execute("SELECT COUNT(*), COALESCE(SUM(seatable), 0) FROM births").fetchone()
    last = store.db.execute("SELECT night FROM birth_candidates ORDER BY night DESC LIMIT 1").fetchone()
    night_ = None
    if last is not None:
        counts = {str(r[0]): int(r[1]) for r in store.db.execute(
            "SELECT status, COUNT(*) FROM birth_candidates WHERE night=? GROUP BY status", (last[0],))}
        night_ = {"night": str(last[0]), **counts, "usd": round(spent(store, dt.date.fromisoformat(str(last[0]))), 4)}
    call = store.db.execute("SELECT night, status, usd, asked_at, answered_at FROM birth_calls ORDER BY night DESC, "
                            "answered_at DESC LIMIT 1").fetchone() if "birth_calls" in _tables(store.db) else None
    last_call = None
    if call is not None:
        try:
            seconds = round((S.parse_iso(call["answered_at"]) - S.parse_iso(call["asked_at"])).total_seconds(), 1)
        except (TypeError, ValueError):
            seconds = None
        last_call = {"night": str(call["night"]), "status": str(call["status"]), "usd": round(float(call["usd"] or 0), 4),
                     "seconds": seconds}
    return {"registered": int(reg[0]), "seatable": int(reg[1]), "records": int(reg[0]) - int(reg[1]),
            "last_night": night_, "last_call": last_call}


__all__ = ["GRAMMAR", "FIELDS", "FAMILIES", "ENTRY", "RULE_FIELDS", "RANKS", "ITEMS_8K", "READ_ITEMS_8K", "SpecError",
           "parse", "canonical", "sha", "reads", "control_spec", "control_id", "program", "registered_programs",
           "select", "unread_reaction", "outcome_free", "Facts", "jaccard", "budget", "budget_used_tenths", "validate",
           "SYSTEM", "USER", "prompt_sha", "render", "request_body", "worst_usd", "parse_answer", "propose", "path_of",
           "line_of", "register", "reconcile", "night", "summary", "SESSIONS", "MIN_RATE", "MIN_RECORDED",
           "RECORD_MIN_RATE", "recorded_sessions", "JACCARD_MAX", "CHARGE_TENTHS", "BUDGET_TENTHS", "SEATABLE_A_NIGHT",
           "K", "NIGHT_USD", "MODEL", "EFFORT", "PRICES", "GEO_MAX", "FACTS_DENY", "DOCS_ROUTE", "JOB", "ID_PREFIX",
           "canonical_name", "renamed", "EXAMPLES", "PARSE_VERSION", "PARSE_VERSION_BEFORE", "RERUN_BY", "rerun_due",
           "STREAM", "THINKING", "CALL_LIMIT", "STREAM_GAP", "LOST", "UNANSWERED", "ASKED", "CHARGE_HUNDREDTHS",
           "BUDGET_HUNDREDTHS", "budget_used_hundredths", "budget_waiting_hundredths", "RESERVED",
           "budget_reserved_hundredths"]
