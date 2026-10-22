// THE DAILY ONE-SCREEN REPORT (release 1019c; the owner's goal of Oct 19, 2026, item 5, and its last line: "Report
// account-shown profit first, Net after costs beside it"): the House's stall job sends league/ops/daily_report.py's facts
// once a New York day as a `report` notice, and this composes every word: one screen on a phone (no line over 60
// characters), account-shown profit first and Net after costs beside it, the day's MEASURED metered compute against its
// cap ("OVER" when above it) with the cap's lines labelled the allowance, then the day's events, verdicts, real fills and
// shadow intents, each real-money program's band, settled n, P&L and evidence, the buy-and-hold, the expected false
// passes and the alarms open. Figures only: no House text is ever echoed. Keyed by its day: once a day.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { composeNotice, composeReport, reportKey, NOTICE_KINDS, REPORT_WIDTH, REPORT_PROGRAMS, STALL_CAUSES } from '../lib/email.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-21T02:20:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const HOUR = 3600000;
const env = (extra = {}) => ({ GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', CAP_TIMEZONE: 'America/New_York', ...extra });
//: The House's facts (invented figures; league/tests/test_daily_report.py holds the House's keys equal to this file's).
const { _note: _ignored, ...REPORT } = JSON.parse(readFileSync(new URL('../../league/tests/fixtures/daily_report.json', import.meta.url), 'utf8'));
const lines = facts => composeNotice(facts).text.split('\n');

test('the report is its own notice kind, keyed by its day, and every line fits a phone', () => {
  assert.ok(NOTICE_KINDS.includes('report'));
  assert.equal(reportKey(REPORT), 'report:2026-10-20');
  const message = composeNotice(REPORT);
  assert.equal(message.subject, 'LTCM daily 2026-10-20: shown +$2.94, net -$0.39; 2 alarms');
  const text = message.text.split('\n');
  for (const line of text) assert.ok(line.length <= REPORT_WIDTH, `${line.length}: ${line}`);
  // One screen: 44 lines before release 1019f; the day's real buys add three (A80 (2)), the break-even edge a fourth once a
  // Probe buy exists, and the Done line (the goal V2) three; release 1019h's Done supply line its head, a line or two
  // of Probe+ rows and its reach (four for the fixture's two rows).
  // Release 1019i: the attempts ledger's fill rates (two lines an auction), the batched score's settle pace (two) and,
  // its review, the PX line (one).
  assert.ok(text.length <= 62, `one screen: ${text.length} lines`);   // (44 + 3 + 1 + 3 + 4 + 4 + 2 + 1; no Probe buy: 61)
  assert.equal(text.length, 61);
  assert.deepEqual(text.slice(0, 7), [
    'The event lane, 2026-10-20 (New York day).', '',
    'Profit, real money (account-shown | net of costs):',
    ' today:   +$2.94 | -$0.39',
    ' to date: +$2.94 | -$0.39',
    '  since 2026-10-20, 3 settled; costs $3.33', '',
  ]);
  for (const line of [
    'Costs, UTC day, measured 04:00-24:00 UTC: $3.33',
    ' under the day\'s cap of $5.00',
    ' Sail $1.20, Claude $1.97 (verdicts $1.85)',
    ' Cloudflare $0.16, data $0.00',
    ' Allowance: cap $5.00, fixed $1.66, lane $3.00, research',
    '   $0.34',
    ' Yesterday: $4.10 of $5.00',
    'Real fills: 4 buys, 3 sells, fees $0.06',
    ' Fill gap vs the auction (worse +): entry +2.1 bp (3), exit',
    '   -0.5 bp (3)',
    ' ERN-READ-O1 v2 learning: 38 | 2; +$1.47 | -$0.75',
    '  look 1 in 22; market 35%, bench +4.1 bp; b&h +$0.42',
    ' INS-BUY-O1 v2 probe: 61 | 1; +$1.47 | +$0.36',
    '  look 2 in 29; market -12%, bench -2.5 bp',
    'Same-risk buy-and-hold: +$0.42',
    'Expected false passes: 0.9 (0.10 x 9 versions)',
  ]) assert.ok(text.includes(line), line);
  // Account-shown profit first; the costs (with the allowance labelled as such) after it; the alarms worded at the end.
  assert.ok(text.indexOf(' today:   +$2.94 | -$0.39') < text.findIndex(line => line.startsWith('Costs, UTC day')));
  const alarms = text.findIndex(line => line.startsWith('Alarms open:'));
  const said = text.slice(alarms).join(' ').replace(/\s+/g, ' ');
  assert.ok(alarms > 0 && said.includes(STALL_CAUSES.cap_breach) && said.includes(STALL_CAUSES.evl_verdicts), said);
  assert.ok(text.includes('Shadow intents today: ERN-READ-O1 v1:9 v2:9;'));
  assert.ok(text.includes('  INS-BUY-O1 v2:4; 4 skipped'));
  assert.ok(text.includes('Records and controls: 17 versions; today 31; settled 140'));
});

test('over the cap the report says so in its subject and its costs; with no real fill yet, n/a until real fills', () => {
  const over = { ...REPORT, costs: { ...REPORT.costs, spent_usd: 6.36, at_least_usd: 6.36, claude_usd: 5.0, over: true,
    yesterday: { ...REPORT.costs.yesterday, spent_usd: 5.4, over: true } } };
  const message = composeNotice(over);
  assert.equal(message.subject, 'LTCM daily 2026-10-20: shown +$2.94, net -$0.39 (over the cap); 2 alarms');
  const text = message.text.split('\n');
  assert.ok(text.includes(' OVER the day\'s cap of $5.00'));
  assert.ok(text.includes(' Yesterday: $5.40 of $5.00, OVER the cap'));
  const fresh = { ...REPORT, alarms: [], profit: { day: { shown_usd: 0, net_usd: -3.33 },
    to_date: { since: null, shown_usd: null, net_usd: null, metered_usd: null, events: 0 } },
  programs: REPORT.programs.map(p => ({ ...p, real: 0, shown_usd: null, net_usd: null, by_band: [], buy_hold_usd: null })),
  buy_hold: { usd: null, why: 'n/a until real fills' } };
  const quiet = composeNotice(fresh);
  assert.equal(quiet.subject, 'LTCM daily 2026-10-20: no real fills yet; costs $3.33');
  const said = quiet.text.split('\n');
  for (const line of [' today:   +$0.00 | -$3.33', ' to date: n/a until real fills', 'Same-risk buy-and-hold: n/a until real fills',
    ' ERN-READ-O1 v2 learning: 38 | 0; no real event', 'Alarms open: none']) assert.ok(said.includes(line), line);
  // A day whose readings cover it whole; a meter with no reading: at least; the floor's allowance said so.
  const partial = { ...REPORT, costs: { ...REPORT.costs, spent_usd: null, at_least_usd: 1.2, sail_usd: null, whole: true,
    allowance: { ...REPORT.costs.allowance, source: 'floor' } } };
  const words = lines(partial);
  assert.ok(words.includes('Costs, UTC day, measured the whole day: $1.20 at least'));
  assert.ok(words.includes(' Sail unknown, Claude $1.97 (verdicts $1.85)'));
  assert.ok(words.some(line => line.startsWith(' Allowance (the floor): cap $5.00')));
  // The first run after a deploy: no meter read yet in the day.
  const unread = lines({ ...REPORT, costs: { ...REPORT.costs, from: null, to: null, spent_usd: null, at_least_usd: 0.16,
    sail_usd: null, claude_usd: null } });
  assert.ok(unread.includes('Costs, UTC day, no meter read yet: $0.16 at least'));
  // COSTS TO DATE AS FAR AS THE METERS COVER THEM (the review of r2/alarms, its major 2): a ledger begun a day after the
  // first fill, and a day a meter missed, are said in the body and the subject; never a silent Net.
  const late = { ...REPORT, profit: { ...REPORT.profit, to_date: { ...REPORT.profit.to_date, costs_from: '2026-10-21',
    partial: true, missing: ['2026-10-22', 'last week'] } } };
  const lateMail = composeNotice(late);
  assert.equal(lateMail.subject, 'LTCM daily 2026-10-20: shown +$2.94, net -$0.39 (costs partial); 2 alarms');
  const lateText = lateMail.text.split('\n');
  for (const line of lateText) assert.ok(line.length <= REPORT_WIDTH, line);
  const lateWords = lateText.join(' ').replace(/\s+/g, ' ');
  assert.ok(lateWords.includes('since 2026-10-20, 3 settled; costs $3.33 since 2026-10-21, partly measured'), lateWords);
  assert.ok(lateWords.includes('a meter unread on 2026-10-22') && !lateWords.includes('last week'));
  const partlySame = lines({ ...REPORT, profit: { ...REPORT.profit, to_date: { ...REPORT.profit.to_date, partial: true } } });
  assert.ok(partlySame.includes('  since 2026-10-20, 3 settled; costs $3.33 since 2026-10-20,')
    && partlySame.includes('   partly measured'), partlySame.join('|'));
  assert.ok(!lines(REPORT).join(' ').includes('partly'), 'a ledger that covers it all: no label');
  // The lane's own report job did not run: said.
  assert.ok(lines({ ...REPORT, lane_report: false }).includes('The lane\'s own report job did not run for this day.'));
  // A program on real money in two bands has a line for each.
  const banded = { ...REPORT, programs: [{ ...REPORT.programs[1], real: 3, by_band: [{ band: 'learning', n: 2, shown_usd: -0.4, net_usd: -0.9 },
    { band: 'probe', n: 1, shown_usd: 1.47, net_usd: 1.2 }] }] };
  const banding = lines(banded);
  assert.ok(banding.includes('  learning 2: -$0.40 | -$0.90') && banding.includes('  probe 1: +$1.47 | +$1.20'));
});

test('figures only: House text where a figure goes is never echoed; a program, a band or an alarm that is not one is left out', () => {
  const odd = {
    ...REPORT, at: 'Apple beats',
    profit: { day: { shown_usd: 'AAPL 182.50', net_usd: Infinity }, to_date: { since: 'last week', shown_usd: 1, net_usd: 'x', events: 'many', metered_usd: -1 } },
    costs: { ...REPORT.costs, from: 'the open', sail_usd: '1.20', allowance: { source: 'Apple', cap_usd: 'lots' } },
    events: { '8k_202': 'Apple beats', news: -1, form4: 1.5 },
    intents: [{ id: 'Apple Inc', version: 1, n: 3 }, { id: 'EVL-OK', version: 'two', n: 1 }, { id: 'EVL-OK', version: 2, n: -4 }],
    programs: [{ ...REPORT.programs[0], id: 'Apple Inc beats estimates' },
      { ...REPORT.programs[0], id: 'EVL-OK', band: 'moonshot', shadow_tradable: '38', market_share_pct: 'AAPL', bench_mean_bp: NaN },
      { ...REPORT.programs[0], id: 'EVL-NOVERSION', version: 0 }],
    alarms: ['cap_breach', 'Apple beats', '__proto__', 'toString'],
    expected_false_passes: 'AAPL', seatable_versions: 9.5,
  };
  const text = composeNotice(odd).text;
  for (const banned of ['Apple', 'AAPL', '182.50', 'lots', 'Infinity', 'NaN', 'moonshot', 'last week', 'the open', 'many', 'NOVERSION']) {
    assert.equal(text.includes(banned), false, banned);
  }
  for (const line of text.split('\n')) assert.ok(line.length <= REPORT_WIDTH, line);
  assert.ok(text.includes(' OK v2 unknown: unknown | 2;'));
  assert.ok(text.includes('Events: 8-K 2.02 unknown, other 8-K unknown, Form 4'));
  assert.ok(text.includes('Shadow intents today: none'));
  assert.ok(text.replace(/\s+/g, ' ').includes(`Alarms open: ${STALL_CAUSES.cap_breach}`) && !text.includes('toString'));
  assert.ok(text.includes('At: an unknown time.'));
  for (const bad of [undefined, null, 'report', [REPORT], { ...REPORT, day: 'yesterday' }, { ...REPORT, day: undefined }]) {
    assert.equal(composeReport(bad ?? undefined), null, JSON.stringify(bad)?.slice(0, 40));
    assert.equal(composeNotice({ ...(bad && typeof bad === 'object' && !Array.isArray(bad) ? bad : {}), kind: 'report',
      day: bad?.day }), null);
  }
  // At most REPORT_PROGRAMS programs, and the worst widths still fit a phone.
  const many = { ...REPORT, programs: Array.from({ length: 40 }, (_, i) => ({ ...REPORT.programs[0], id: `EVL-NEWS-REACT-ON${i}`,
    band: 'learning', shadow_tradable: 999999, real: 99999, shown_usd: -999999.99, net_usd: -999999.99,
    next_look: 10, events_to_go: 2250, market_share_pct: -9999, bench_mean_bp: -99999.9, buy_hold_usd: -999999.99 })) };
  const big = lines(many);
  assert.equal(big.filter(line => line.startsWith(' NEWS-REACT-ON')).length, REPORT_PROGRAMS);
  for (const line of big) assert.ok(line.length <= REPORT_WIDTH, `${line.length}: ${line}`);
});

test('the composer reads every fact the House writes', () => {
  const read = new Set();
  const spy = (value, prefix) => (value && typeof value === 'object'
    ? new Proxy(value, { get: (target, key) => (typeof key === 'string' && read.add(`${prefix}${key}`), spy(target[key], `${prefix}${String(key)}.`)) })
    : value);
  // Each program in two bands, so its by_band lines are read too.
  // (Release 1019f: and a Probe buy on record, so the break-even edge is read too.)
  const twoBands = { ...REPORT, programs: REPORT.programs.map(p => ({ ...p, by_band: [...p.by_band, { ...p.by_band[0], band: 'sized' }] })),
    break_even: { ...REPORT.break_even, since: '2026-10-22', compute_per_session: 3.5, probe_per_session: 60, edge_bp: 583.3 },
    // (Release 1019h: and a checkpoint not within the projection's horizon, so the horizon is read too.)
    supply: { ...REPORT.supply, checkpoint_in: null } };
  composeReport(spy(twoBands, ''));
  const want = new Set();
  const walk = (value, prefix) => {
    for (const [key, inner] of Object.entries(value)) {
      want.add(`${prefix}${key}`);
      if (Array.isArray(inner)) inner.forEach(item => (item && typeof item === 'object' ? walk(item, `${prefix}${key}.*.`) : null));
      else if (inner && typeof inner === 'object') walk(inner, `${prefix}${key}.`);
    }
  };
  walk(REPORT, '');
  const seen = new Set([...read].map(key => key.replace(/\.\d+\./g, '.*.')));
  // Read by the router, not the composer (`kind`, `notice_id`), or kept for the House's own record (a program's
  // `intents`, its `buy_hold_why` and the total's `why`: the gateway words n/a itself and echoes no House text).
  // (Release 1019f: `entries.why` and `break_even.why` likewise: the gateway words "none" and "n/a" itself.)
  // (Release 1019h: `supply.why` likewise: the gateway words "no Probe+ row yet" itself.)
  const unread = ['kind', 'notice_id', 'programs.*.intents', 'programs.*.buy_hold_why', 'buy_hold.why', 'costs.allowance.cap_usd',
    'entries.why', 'break_even.why', 'supply.why'];
  const missed = [...want].filter(key => !seen.has(key) && !unread.includes(key));
  assert.deepEqual(missed, [], 'every fact the House writes is read');
});

test('the day\'s real buys (A80 (2)): filled of planned, the venue\'s cancels and the re-sends, the never-sent by reason, the bound of each auction; the break-even edge once a Probe buy exists', () => {
  const text = lines(REPORT);
  for (const line of ['Real buys 7/9 filled; venue cancels 2 (re-sent 1, filled 1)',
    ' never sent 1 (cash 1); not filled 0; room cut 2', ' By auction: open 4/6 bound cash; close 3/3 bound room']) {
    assert.ok(text.includes(line), line);
  }
  assert.ok(!text.some(line => line.startsWith('Break-even')), 'no Probe buy yet: no line');
  const probe = lines({ ...REPORT, break_even: { since: '2026-10-22', compute_per_session: 3.5, probe_per_session: 60,
    edge_bp: 583.3, partial: false, why: null } });
  assert.ok(probe.includes('Break-even edge +583.3 bp ($3.50 / $60.00 Probe, a session)'), probe.join('|'));
  const unmeasured = lines({ ...REPORT, break_even: { ...REPORT.break_even, since: '2026-10-22', why: 'n/a: the meters' } });
  assert.ok(unmeasured.includes('Break-even edge: n/a (compute not measured)'));
  // Only the House's own names are worded; anything else is left out or reads unknown, never echoed.
  const odd = lines({ ...REPORT, entries: { auctions: [{ at: 'Apple', planned: 3, filled: 1, bound: 'cash' },
    { at: 'open', planned: 2, filled: 'AAPL', bound: 'AAPL 182.50' }],
  totals: { ...REPORT.entries.totals, never: { cash: 2, 'Apple beats': 4, room: -1, budget: 1.5 }, filled: 'x' } } }).join(' ');
  for (const banned of ['Apple', 'AAPL', '182.50']) assert.equal(odd.includes(banned), false, banned);
  assert.ok(odd.includes('Real buys unknown/9 filled') && odd.includes('never sent 1 (cash 2)'), odd);
  assert.ok(odd.includes('By auction: open unknown/2 bound none'), odd);
  assert.ok(lines({ ...REPORT, entries: { auctions: [], totals: { ...REPORT.entries.totals, planned: 0 }, why: null } })
    .includes('Real buys: none planned today'));
  assert.ok(!lines({ ...REPORT, entries: undefined }).some(line => line.startsWith('Real buys')), 'an older House: no line');
});

test('through /v1/notify: one mail a day, keyed by its day, whatever id the House sends; a report with no day is refused', async () => {
  const gate = createGate({ store: memoryStore(), env: env(), now: () => NOW });
  const sent = [];
  const post = (facts, at) => route(new Request(`${GATEWAY}/v1/notify`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(facts),
  }), env(), { gate, now: () => at, mailer: async message => void sent.push(message) });
  assert.equal((await (await post(REPORT, NOW)).json()).sent, true);
  assert.equal((await (await post({ ...REPORT, notice_id: 'another-id' }, NOW + HOUR)).json()).duplicate, true, 'the same day');
  assert.equal((await (await post({ ...REPORT, day: '2026-10-21' }, NOW + 24 * HOUR)).json()).sent, true, 'the next day');
  assert.equal(sent.length, 2);
  assert.equal(sent[0].subject, 'LTCM daily 2026-10-20: shown +$2.94, net -$0.39; 2 alarms');
  assert.equal((await post({ ...REPORT, day: 'today' }, NOW + 25 * HOUR)).status, 400);
  assert.equal(sent.length, 2);
});

test('the Done line: Probe+ events toward 300 by program, the next checkpoint and the bound (the goal V2)', () => {
  const text = lines(REPORT);
  const at = text.findIndex(line => line.startsWith('Done, Probe+ real events:'));
  assert.ok(at > 0, text.join('\n'));
  assert.deepEqual(text.slice(at, at + 3), [
    'Done, Probe+ real events: 120 of 300, next at 200',
    ' bound +12.5 bp (net of bench -3.1 bp); learning 46 beside',
    ' ERN-READ-O1 70; INS-BUY-O1 50',
  ]);
  for (const line of text) assert.ok(line.length <= REPORT_WIDTH, `${line.length}: ${line}`);
  const unread = lines({ ...REPORT, done: { ...REPORT.done, counted: null, by_program: [] } });
  assert.ok(unread.includes('Done, Probe+ real events: not read yet'), unread.join('\n'));
  const flags = lines({ ...REPORT, done: { ...REPORT.done, holds: true, pivot: true, stop: true } }).join(' ');
  for (const words of ['DONE at a checkpoint', 'PIVOT: retire the lane', '$800 SPENT: stop all spend']) assert.ok(flags.includes(words), words);
  const before = lines({ ...REPORT, done: undefined });
  assert.ok(!before.some(line => line.startsWith('Done,')), 'a House before the reader sends no done block: no line');
});

test('the Done supply line (release 1019h, SUP-4): each Probe+ row\'s counted events, its measured picks a session, its projected session to 50 at the stated seasons, and a flag under 3 rows', () => {
  const text = lines(REPORT);
  for (const line of ['Done supply, Probe+ (seasons stated, not measured):',
    ' INS-BUY-O1 50, 1.4/session, 50 reached, under 2 (cash);', ' NEWS-READ-O1 0, 4.2/session, 50 in 14 (2026-11-09)',
    ' FLAG: 2 of 2 reach 50 by 300 (in 38 sessions); needs 3']) {
    assert.ok(text.includes(line), `${line} | ${text.join('|')}`);
  }
  const three = lines({ ...REPORT, supply: { ...REPORT.supply, reach: 3, flag: false, checkpoint_in: null,
    rows: [...REPORT.supply.rows, { ...REPORT.supply.rows[1], id: 'EVL-ERN-READ-O1', band: 'sized', decisions: 2, to_50: null }] } });
  assert.ok(three.includes('   ERN-READ-O1 sized 0, 4.2/session (2 read), 50 not in reach') ||
    three.some(line => line.includes('ERN-READ-O1 sized 0, 4.2/session (2 read), 50 not in reach')), three.join('|'));
  assert.ok(three.includes(' 3 of 3 reach 50 by 300 (not within 250 sessions)'), three.join('|'));
  assert.ok(!three.some(line => line.includes('FLAG')));
  const none = lines({ ...REPORT, supply: { ...REPORT.supply, rows: [], reach: 0, flag: true, why: 'no Probe+ row yet <b>' } });
  assert.ok(none.includes('Done supply: no Probe+ row yet (Done needs 3 x 50)'));
  assert.ok(!none.join('\n').includes('<b>'), 'the House\'s words are never echoed');
  const bad = lines({ ...REPORT, supply: { ...REPORT.supply, rows: [{ ...REPORT.supply.rows[0], id: 'ACME SURGES' },
    { ...REPORT.supply.rows[0], under_bound: '<script>' }] } });
  assert.ok(!bad.join('\n').includes('ACME') && !bad.join('\n').includes('<script>'), bad.join('|'));
  for (const line of [...text, ...three, ...none, ...bad]) assert.ok(line.length <= REPORT_WIDTH, line);
  const before = lines((({ supply: _s, ...rest }) => rest)(REPORT));
  assert.ok(!before.some(line => line.startsWith('Done supply')), 'a House before release 1019h: no line');
});

test('release 1019i: the fill rates by auction over 3 and 20 sessions (the attempts ledger) and the settle pace (the batched score)', () => {
  const text = lines(REPORT);
  for (const line of ['Fills open: 10/12 83% (3 sessions), 63/70 90% (20)',
    ' venue cancels 2/14, 8/78; re-sent 2, 7; unsent 1, 4',
    'Fills close: 9/9 100% (3 sessions), 50/52 96% (20)',
    ' venue cancels 0/9, 1/53; re-sent 0, 1; unsent 0, 2',
    'Score: 398/412 settled, 3 passes, 4.0 min, 99/min, batched',
    ' skip 9, wait 5, fail 0; bars 12, prints 806; parity 20/20']) {
    assert.ok(text.includes(line), line);
  }
  // No ledger yet (every figure null) and no score pass of the night: no line of either.
  const empty = Object.fromEntries(Object.keys(REPORT.fill_rates).map(a => [a, {
    last3: Object.fromEntries(Object.keys(REPORT.fill_rates[a].last3).map(k => [k, null])),
    last20: Object.fromEntries(Object.keys(REPORT.fill_rates[a].last20).map(k => [k, null]))}]));
  const quiet = lines({ ...REPORT, fill_rates: empty, settle: { ...REPORT.settle, passes: 0 } });
  assert.ok(!quiet.some(line => line.startsWith('Fills ') || line.startsWith('Score:')), quiet.join('\n'));
  // A night not complete says so, the per-intent path says nothing of batching, no parity night says nothing of it.
  const partial = lines({ ...REPORT, settle: { ...REPORT.settle, complete: false, batched: 0, parity: { checked: 0, equal: 0 } } });
  assert.ok(partial.includes('Score: 398/412 settled, 3 passes, 4.0 min, 99/min, not'), partial.join('\n'));
  assert.ok(partial.includes(' skip 9, wait 5, fail 0; bars 12, prints 806'));
  // Figures only: a word where a figure goes is never echoed.
  const odd = lines({ ...REPORT, settle: { ...REPORT.settle, settled: 'ACME rallied' }, fill_rates: { ...REPORT.fill_rates,
    open: { ...REPORT.fill_rates.open, last3: { ...REPORT.fill_rates.open.last3, buys_filled: 'ACME' } } } });
  assert.ok(!odd.join('\n').includes('ACME'));
});

test('release 1019i\'s review: the parity latch on the Score lines and the PX line (sizes and counts only)', () => {
  const text = lines(REPORT);
  assert.ok(text.includes('PX store: 812/2048 MB, 41.2 GB free; runs 12 ok, 1 partial'), text.join('\n'));
  assert.ok(!text.some(line => line.includes('BATCHED SCORE OFF')), 'no latch: nothing said');
  const latched = lines({ ...REPORT, settle: { ...REPORT.settle, latched: true } });
  assert.ok(latched.includes(' BATCHED SCORE OFF: a parity difference latched it'), latched.join('\n'));
  // No room: said, with the floor; the recorders off but px.sqlite on disk: "(off)".
  const full = lines({ ...REPORT, px_store: { ...REPORT.px_store, ok: false, free_gb: 3.2,
    runs: { ...REPORT.px_store.runs, disk: 4 } } });
  const said = full.join(' ').replace(/\s+/g, ' ');     // (the line wraps at the phone's width)
  assert.ok(said.includes('3.2 GB free; runs 12 ok, 1 partial, 4 disk; NO ROOM (floor 5.0 GB): nothing written'), said);
  const off = lines({ ...REPORT, px_store: { ...REPORT.px_store, on: false } });
  assert.ok(off.some(line => line.startsWith('PX store (off): 812/2048 MB')), off.join('\n'));
  // The recorders off and no px.sqlite (every figure null): no line at all.
  const none = lines({ ...REPORT, px_store: { on: false, size_mb: null, line_mb: null, free_gb: null, floor_gb: null,
    ok: null, runs: Object.fromEntries(Object.keys(REPORT.px_store.runs).map(k => [k, null])) } });
  assert.ok(!none.some(line => line.startsWith('PX store')), none.join('\n'));
  // Figures only: a word where a figure goes is never echoed.
  const odd = lines({ ...REPORT, px_store: { ...REPORT.px_store, size_mb: 'ACME', runs: { ok: 'ACME', ACME: 3 } } });
  assert.ok(!odd.join('\n').includes('ACME'), odd.join('\n'));
});
