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
  assert.ok(text.length <= 45, `one screen: ${text.length} lines`);
  assert.deepEqual(text.slice(0, 7), [
    'The event lane, 2026-10-20 (New York day).', '',
    'Profit, real money (account-shown | net of costs):',
    ' today:   +$2.94 | -$0.39',
    ' to date: +$2.94 | -$0.39',
    '  since 2026-10-20, 3 settled; costs $3.33', '',
  ]);
  for (const line of [
    'Costs, measured 00:00-22:20 ET: $3.33',
    ' under the day\'s cap of $5.00',
    ' Sail $1.20, Claude $1.97 (verdicts $1.85)',
    ' Cloudflare $0.16, data $0.00',
    ' Allowance: cap $5.00, fixed $1.66, lane $3.00, research',
    '   $0.34',
    ' Yesterday: $4.10 of $5.00',
    'Real fills: 4 buys, 3 sells, fees $0.06',
    ' ERN-READ-O1 v2 learning: 38 | 2; +$1.47 | -$0.75',
    '  look 1 in 22; market 35%, bench +4.1 bp; b&h +$0.42',
    ' INS-BUY-O1 v2 probe: 61 | 1; +$1.47 | +$0.36',
    '  look 2 in 29; market -12%, bench -2.5 bp',
    'Same-risk buy-and-hold: +$0.42',
    'Expected false passes: 0.9 (0.10 x 9 versions)',
  ]) assert.ok(text.includes(line), line);
  // Account-shown profit first; the costs (with the allowance labelled as such) after it; the alarms worded at the end.
  assert.ok(text.indexOf(' today:   +$2.94 | -$0.39') < text.findIndex(line => line.startsWith('Costs, measured')));
  const alarms = text.findIndex(line => line.startsWith('Alarms open:'));
  assert.ok(alarms > 0 && text.slice(alarms, alarms + 3).join(' ').includes(STALL_CAUSES.cap_breach));
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
  assert.ok(words.includes('Costs, measured the whole day: $1.20 at least'));
  assert.ok(words.includes(' Sail unknown, Claude $1.97 (verdicts $1.85)'));
  assert.ok(words.some(line => line.startsWith(' Allowance (the floor): cap $5.00')));
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
  assert.ok(text.includes(`Alarms open: ${STALL_CAUSES.cap_breach}`) && !text.includes('toString'));
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
  const twoBands = { ...REPORT, programs: REPORT.programs.map(p => ({ ...p, by_band: [...p.by_band, { ...p.by_band[0], band: 'sized' }] })) };
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
  const unread = ['kind', 'notice_id', 'programs.*.intents', 'programs.*.buy_hold_why', 'buy_hold.why', 'costs.allowance.cap_usd'];
  const missed = [...want].filter(key => !seen.has(key) && !unread.includes(key));
  assert.deepEqual(missed, [], 'every fact the House writes is read');
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
