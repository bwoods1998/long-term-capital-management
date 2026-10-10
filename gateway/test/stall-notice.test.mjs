// The stall notice (the owner's goal of Oct 7, 2026, item 6): the House's `stall` job (league/ops/stall.py
// `notice_facts`) composed into one short mail listing every cause standing. Its subject says "needs you" and the causes
// with an owner step when there is one, else "stalled" and every cause, in this file's words; its body opens with the
// owner steps (or says nothing needs the owner), then each cause: the House's sentence, its figures, how long, what the
// House is doing. Mailed at most every 12 hours for the same owner causes (a new one at once) and every 24 hours when
// nothing needs the owner, whatever id the House sends, inside the day's notice cap.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { route } from '../lib/router.mjs';
import { createGate, STALL_NOTICE_MS, STALL_INFO_MS } from '../lib/gate.mjs';
import { composeNotice, NOTICE_KINDS, STALL_CAUSES, stallKey, FLOOR, CONSOLE } from '../lib/email.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-07T10:20:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const HOUR = 3600000;
const env = (extra = {}) => ({ GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', CAP_TIMEZONE: 'America/New_York', ...extra });
const STALL_SOURCE = readFileSync(new URL('../../league/ops/stall.py', import.meta.url), 'utf8');

//: One cause as league/ops/stall.py `cause_facts` writes it: a births stall of Oct 7 (no birth since 08:12Z the day
//: before, the population under its ceiling), nothing the owner must do.
const BIRTHS = {
  cause: 'births',
  what: 'No family was born in the last 12 h while the population is 41 of a ceiling of 64.',
  numbers: { births_12h: 0, population: 41, ceiling: 64, last_birth_at: '2026-10-06T08:12:00Z', architect_passes_12h: 24 },
  since: '2026-10-06T08:12:00Z', hours: '26.1',
  doing: 'The architect passed 24 times in the last 12 h: 24 found no cell a birth may land in.',
  owner_step: null,
};
const RUNWAY = {
  cause: 'runway_sail', what: 'Sail holds 2.4 days of research at the ceiling above its reserve (under 3).',
  numbers: { runway_days_at_ceiling: 2.4, runway_days_held: 5, research_usd_day: 9.6, ceiling_usd_day: 15, topup_usd: 112, card_date: '2026-10-05' },
  since: '2026-10-07T04:20:00Z', hours: '6.0', doing: 'The budget rule tapers research on Sail to what it holds.',
  owner_step: 'top up Sail: about $112.00 buys 7 more days of research at the ceiling (the taper starts 2026-10-05)',
};
const notice = (...causes) => ({ kind: 'stall', notice_id: 'stall:x', causes, at: '2026-10-07T10:20:00Z' });
const NONE_NEEDED = 'Nothing here needs you: the House keeps working around it, and says so again in 24 hours if it still stands.';
const END = ['', FLOOR, CONSOLE, ''];

test('a stall that needs nothing from the owner says so first, then each cause: its words, the House\'s sentence, the numbers, how long, what the House is doing', () => {
  assert.ok(NOTICE_KINDS.includes('stall'));
  const message = composeNotice(notice(BIRTHS));
  assert.equal(message.subject, 'LTCM: stalled: no births');
  assert.deepEqual(message.text.split('\n'), [
    NONE_NEEDED, '',
    'Stalled: no births.', BIRTHS.what,
    'The numbers:', '- births_12h: 0', '- population: 41', '- ceiling: 64', '- last_birth_at: 2026-10-06T08:12:00Z',
    '- architect_passes_12h: 24',
    'How long: 26.1 hours, since 2026-10-06T08:12:00Z.',
    `What the House is doing: ${BIRTHS.doing}`, '',
    'At: 2026-10-07T10:20:00Z.', ...END,
  ]);
});

test('every cause standing is in one mail; an owner step leads it, in its subject and its first lines', () => {
  const gym = { ...BIRTHS, cause: 'gym_runs', what: 'The Gym evaluated 3 programs in the last 6 h (fewer than 10).', numbers: {} };
  const both = composeNotice(notice(RUNWAY, BIRTHS, gym));
  assert.equal(both.subject, 'LTCM: needs you: Sail research runway short');
  const lines = both.text.split('\n');
  assert.deepEqual(lines.slice(0, 3), [
    'Only you can do this; the House keeps working around it meanwhile:',
    '- top up Sail: about $112.00 buys 7 more days of research at the ceiling (the taper starts 2026-10-05).', '',
  ]);
  for (const line of ['Stalled: Sail research runway short.', 'Stalled: no births.', 'Stalled: too few Gym runs.', '- topup_usd: 112',
    'How long: 6 hours, since 2026-10-07T04:20:00Z.',
    'Only you can do this: top up Sail: about $112.00 buys 7 more days of research at the ceiling (the taper starts 2026-10-05).']) {
    assert.ok(lines.includes(line), line);
  }
  assert.equal(both.text.includes('Nothing here needs you'), false);
  // With no owner step the subject names every cause, at most three by name.
  assert.equal(composeNotice(notice(BIRTHS, gym)).subject, 'LTCM: stalled: no births, too few Gym runs');
  const four = ['births', 'gym_runs', 'validations', 'braked'].map(cause => ({ ...BIRTHS, cause }));
  assert.equal(composeNotice(notice(...four)).subject, 'LTCM: stalled: no births, too few Gym runs, no Validation verdicts and 1 more');
  // A step the House ended with its own full stop is not said with two.
  const deploy = composeNotice(notice({ ...BIRTHS, cause: 'owner_deploy', owner_step: 'merge the running release to main.' }));
  assert.equal(deploy.subject, 'LTCM: needs you: an owner deploy is waiting');
  assert.ok(deploy.text.includes('- merge the running release to main.\n'));
});

test('every cause the House can name has its words here; no other cause, no empty or repeated list, is composed', () => {
  // The House's own list (league/ops/stall.py CAUSES): a cause added there must be worded here, not refused.
  const listed = /\nCAUSES = \(([^)]*)\)/.exec(STALL_SOURCE);
  assert.ok(listed, 'league/ops/stall.py names its causes in one tuple');
  const causes = [...listed[1].matchAll(/"([a-z_]+)"/g)].map(match => match[1]);
  assert.deepEqual([...causes].sort(), Object.keys(STALL_CAUSES).sort());
  for (const cause of causes) {
    assert.equal(composeNotice(notice({ ...BIRTHS, cause })).subject, `LTCM: stalled: ${STALL_CAUSES[cause]}`, cause);
  }
  assert.ok(composeNotice(notice(...causes.map(cause => ({ ...BIRTHS, cause })))), 'every cause at once');
  for (const cause of ['', undefined, null, 'BIRTHS', 'births\nBcc: x', '__proto__', 'toString', 'funding']) {
    assert.equal(composeNotice(notice({ ...BIRTHS, cause })), null, String(cause));
  }
  const tooMany = Array.from({ length: causes.length + 1 }, (_, i) => ({ ...BIRTHS, cause: causes[i % causes.length] }));
  for (const list of [undefined, null, [], 'births', { births: BIRTHS }, [BIRTHS, BIRTHS], [BIRTHS, null], [BIRTHS, [1]], tooMany]) {
    assert.equal(composeNotice({ kind: 'stall', causes: list }), null, JSON.stringify(list));
    assert.equal(stallKey({ kind: 'stall', causes: list }), null);
  }
});

test('the composer reads every fact the House writes, and no fact it does not write', () => {
  const written = /\ndef cause_facts\([\s\S]*?\n    return \{([\s\S]*?)\}\n/.exec(STALL_SOURCE);
  assert.ok(written, 'league/ops/stall.py cause_facts returns its facts as one dict');
  const keys = [...written[1].matchAll(/"([a-z_]+)":/g)].map(match => match[1]).sort();
  assert.deepEqual(keys, Object.keys(BIRTHS).sort(), 'the fixture is the House\'s shape');
  const outer = /\ndef notice_facts\([\s\S]*?\n    return \{([\s\S]*?)\}\n/.exec(STALL_SOURCE);
  assert.deepEqual([...outer[1].matchAll(/"([a-z_]+)":/g)].map(match => match[1]).sort(), Object.keys(notice(BIRTHS)).sort());
  const read = new Set();
  const spy = (facts, prefix) => new Proxy(facts, { get: (target, key) => (read.add(`${prefix}${String(key)}`), target[key]) });
  composeNotice(spy({ ...notice(spy({ ...RUNWAY }, 'cause.')) }, ''));
  // `notice_id` is the router's (it keys a stall by its owner causes); `desk_name` is read for every kind.
  const seen = [...read].filter(key => !['desk_name', 'notice_id'].includes(key) && !key.startsWith('cause.then'));
  assert.deepEqual(seen.filter(key => !key.startsWith('cause.')).sort(), ['at', 'causes', 'kind']);
  assert.deepEqual(seen.filter(key => key.startsWith('cause.')).map(key => key.slice(6)).sort(), keys);
});

test('a figure is echoed only as a decimal, a time, yes or no, or a short token; a name that is not a lower-case word is dropped; the House\'s text stays on its line', () => {
  const odd = composeNotice(notice({
    ...BIRTHS,
    what: 'Line one\nBcc: someone@example.com\r\nline two',
    numbers: {
      count: 3, share: '0.25', flag: true, off: false, when: '2026-10-07', causes: 'research_budget,under_line', sha: 'a3f2a629bc01',
      none: null, words: 'the swarm said <b>hi</b>', inf: Infinity, nan: NaN, nested: { a: 1 }, list: [1], long: 'x'.repeat(81),
      'Bad Name': 1, 'bcc\nx': 2, __proto__x: 3,
    },
    hours: 'soon', since: 'yesterday', doing: 'a\u0000b\tc', owner_step: '   ',
  }));
  const lines = odd.text.split('\n');
  assert.equal(lines[0], NONE_NEEDED, 'a blank step is no step');
  assert.equal(lines[3], 'Line one Bcc: someone@example.com line two');
  assert.deepEqual(lines.slice(4, 19), [
    'The numbers:', '- count: 3', '- share: 0.25', '- flag: yes', '- off: no', '- when: 2026-10-07', '- causes: research_budget,under_line',
    '- sha: a3f2a629bc01', '- none: unknown', '- words: unknown', '- inf: unknown', '- nan: unknown', '- nested: unknown',
    '- list: unknown', '- long: unknown',
  ]);
  for (const name of ['Bad Name', 'bcc', '__proto__']) assert.equal(odd.text.includes(name), false, name);
  assert.ok(lines.includes('How long: unknown.'));
  assert.ok(lines.includes('What the House is doing: a b c'));
  for (const echoed of ['<b>', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 'Infinity', 'NaN', '[object']) {
    assert.equal(odd.text.includes(echoed), false, echoed);
  }
  const late = composeNotice({ ...notice(BIRTHS), at: 'x'.repeat(60) });
  assert.ok(late.text.split('\n').includes(`At: ${'x'.repeat(40)}.`));
  // No figures, no sentence: the mail still names the cause and says nothing was given.
  const bare = composeNotice({ kind: 'stall', causes: [{ cause: 'gym_runs' }] });
  assert.deepEqual(bare.text.split('\n'), [
    NONE_NEEDED, '', 'Stalled: too few Gym runs.', 'How long: unknown.', 'What the House is doing: it did not say.', '',
    'At: an unknown time.', ...END,
  ]);
  // At most sixteen figures a cause.
  const many = composeNotice(notice({ ...BIRTHS, numbers: Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`n${i}`, i])) }));
  assert.equal(many.text.split('\n').filter(line => line.startsWith('- n')).length, 16);
});

test('the dedupe key is the owner causes, sorted, or stall:info and every cause; never the id the House sends', () => {
  assert.equal(stallKey(notice(BIRTHS)), 'stall:info:births');
  assert.equal(stallKey(notice({ ...BIRTHS, cause: 'underspend' }, BIRTHS)), 'stall:info:births+underspend');
  assert.equal(stallKey(notice(RUNWAY, BIRTHS)), 'stall:owner:runway_sail');
  const kill = { ...BIRTHS, cause: 'kill_on', owner_step: 'lift the kill switch' };
  assert.equal(stallKey(notice(RUNWAY, kill, BIRTHS)), 'stall:owner:kill_on+runway_sail');
  assert.equal(stallKey(notice(kill, RUNWAY)), 'stall:owner:kill_on+runway_sail');
  assert.equal(stallKey(notice({ ...RUNWAY, owner_step: ' \n ' })), 'stall:info:runway_sail', 'a blank step is no step');
});

test('through /v1/notify: the same owner causes every 12 hours, a new one at once, a stall needing nothing every 24 hours, inside the day\'s cap', async () => {
  assert.equal(STALL_NOTICE_MS, 12 * HOUR);
  assert.equal(STALL_INFO_MS, 24 * HOUR);
  const gate = createGate({ store: memoryStore(), env: env(), now: () => NOW });
  const sent = [];
  const post = (facts, at, settings = {}) => route(new Request(`${GATEWAY}/v1/notify`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(facts),
  }), env(settings), { gate, now: () => at, mailer: async message => void sent.push(message) });
  const info = notice(BIRTHS);
  const first = await (await post(info, NOW)).json();
  assert.deepEqual([first.sent, first.subject], [true, 'LTCM: stalled: no births']);
  // The House retries, loses its own record or sends another id for the same causes: one mail a day.
  for (const [hours, facts] of [[0.5, info], [6, { ...info, notice_id: 'stall:births:other' }], [23.9, { ...info, notice_id: undefined }]]) {
    assert.equal((await (await post(facts, NOW + hours * HOUR)).json()).duplicate, true, `${hours} h later`);
  }
  assert.equal(sent.length, 1);
  // A new cause that needs nothing is not held a day behind one that stands (Oct 10, 2026); the same set again is.
  const more = notice(BIRTHS, { ...BIRTHS, cause: 'birth_yield' });
  assert.equal((await (await post(more, NOW + 12 * HOUR)).json()).sent, true);
  assert.equal((await (await post(more, NOW + 20 * HOUR)).json()).duplicate, true);
  assert.equal(sent.length, 2);
  assert.equal((await (await post(info, NOW + 24 * HOUR)).json()).sent, true);
  assert.equal(sent.length, 3);
  // An owner step is not held behind a stall that needed nothing; the same owner causes wait 12 hours, a new one does not.
  const owner = notice(RUNWAY, BIRTHS);
  assert.equal((await (await post(owner, NOW + 25 * HOUR)).json()).sent, true);
  assert.equal((await (await post({ ...owner, causes: [RUNWAY] }, NOW + 30 * HOUR)).json()).duplicate, true);
  const kill = { ...BIRTHS, cause: 'kill_on', owner_step: 'lift the kill switch' };
  assert.equal((await (await post(notice(RUNWAY, kill), NOW + 31 * HOUR)).json()).sent, true);
  assert.equal((await (await post(owner, NOW + 37 * HOUR)).json()).sent, true, 'twelve hours on, the same causes again');
  assert.equal(sent.length, 6);
  // The day's cap holds for stalls too (here a cap of 1 on a day that has mailed already).
  const capped = await post(notice({ ...RUNWAY, cause: 'runway_claude' }), NOW + 38 * HOUR, { NOTIFY_MAX_PER_DAY: '1' });
  assert.equal(capped.status, 429);
  assert.equal(sent.length, 6);
  // A cause not named, or no list, is refused before anything is counted or mailed.
  assert.equal((await post(notice({ ...BIRTHS, cause: 'nonsense' }), NOW)).status, 400);
  assert.equal((await post({ kind: 'stall', cause: 'births' }, NOW)).status, 400);
  assert.equal(sent.length, 6);
});

test('the causes of Oct 10, 2026: a Done checkpoint and K5 are owner lines; a pre-open FAIL and a late nightly are told as stalls', () => {
  // league/ops/stall.py `_lane_checks`, `_preopen_check` and `_forward_check` (the readiness audit's M6).
  const done = { ...BIRTHS, cause: 'done', what: 'Done criteria hold at a FINAL checkpoint (done_screen at close 30).',
    numbers: { checkpoints: 'done_screen:30', report_at: '2026-10-20T01:30:00Z' },
    owner_step: 'Done holds at a FINAL checkpoint (done_screen at close 30): read the claim in dlane-report.json' };
  assert.equal(composeNotice(notice(done)).subject, 'LTCM: needs you: a Done checkpoint holds');
  assert.ok(composeNotice(notice(done)).text.includes('- checkpoints: done_screen:30\n'));
  const k5 = { ...BIRTHS, cause: 'dlane', numbers: { alarms: 'a4,k5', k5: 'tripped', lane_mode: 'gate' },
    owner_step: 'the direction lane reads shadow while K5 holds: read its losses, then clear it' };
  assert.equal(composeNotice(notice(k5, done)).subject, 'LTCM: needs you: a direction-lane alarm, a Done checkpoint holds');
  assert.equal(stallKey(notice(k5, done)), 'stall:owner:dlane+done');
  const preopen = { ...BIRTHS, cause: 'preopen', numbers: { failed_checks: '6_bands,9_compute' } };
  const forward = { ...BIRTHS, cause: 'forward', numbers: { ready_day: '2026-10-08', expected_day: '2026-10-09' } };
  const both = composeNotice(notice(preopen, forward));
  assert.equal(both.subject, 'LTCM: stalled: a pre-open check failed, the nightly forward replay is late or stopped');
  for (const line of ['- failed_checks: 6_bands,9_compute', '- expected_day: 2026-10-09']) assert.ok(both.text.split('\n').includes(line), line);
});
