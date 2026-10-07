// The stall notice (the owner's goal of Oct 7, 2026, item 6): the House's `stall` job (league/ops/stall.py
// `notice_facts`) composed into one short mail whose subject names the cause in this file's words, whose body carries the
// House's sentence, its figures, how long, what the House is doing and the owner step when there is one; mailed at most
// once per cause per 12 hours whatever id the House sends, inside the day's notice cap.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { route } from '../lib/router.mjs';
import { createGate, STALL_NOTICE_MS } from '../lib/gate.mjs';
import { composeNotice, NOTICE_KINDS, STALL_CAUSES, FLOOR, CONSOLE } from '../lib/email.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-07T10:20:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const HOUR = 3600000;
const env = (extra = {}) => ({ GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', CAP_TIMEZONE: 'America/New_York', ...extra });
const STALL_SOURCE = readFileSync(new URL('../../league/ops/stall.py', import.meta.url), 'utf8');

//: The facts as league/ops/stall.py `notice_facts` writes them: a births stall of Oct 7 (no birth since 08:12Z the day
//: before, the population under its ceiling), nothing the owner must do.
const FACTS = {
  kind: 'stall', notice_id: 'stall:births', cause: 'births',
  what: 'No family was born in the last 12 h while the population is 41 of a ceiling of 64.',
  numbers: { births_12h: 0, population: 41, ceiling: 64, last_birth_at: '2026-10-06T08:12:00Z', architect_passes_12h: 24 },
  since: '2026-10-06T08:12:00Z', hours: '26.1',
  doing: 'The architect passed 24 times in the last 12 h: 24 found no cell a birth may land in.',
  owner_step: null, at: '2026-10-07T10:20:00Z',
};
const NONE_NEEDED = 'Nothing here needs you: the House keeps working around it, and says so again in 12 hours if it still stands.';
const END = ['', FLOOR, CONSOLE, ''];

test('a stall notice names the cause in its subject, then the House\'s sentence, the numbers, how long, what the House is doing, and that nothing needs the owner', () => {
  assert.ok(NOTICE_KINDS.includes('stall'));
  const message = composeNotice(FACTS);
  assert.equal(message.subject, 'LTCM: stalled: no births');
  assert.deepEqual(message.text.split('\n'), [
    FACTS.what, '',
    'The numbers:', '- births_12h: 0', '- population: 41', '- ceiling: 64', '- last_birth_at: 2026-10-06T08:12:00Z',
    '- architect_passes_12h: 24', '',
    'How long: 26.1 hours, since 2026-10-06T08:12:00Z.',
    `What the House is doing: ${FACTS.doing}`,
    NONE_NEEDED,
    'At: 2026-10-07T10:20:00Z.', ...END,
  ]);
});

test('an owner step is said as the one thing only the owner can do, and the House keeps working around it', () => {
  const runway = composeNotice({
    ...FACTS, notice_id: 'stall:runway_sail', cause: 'runway_sail', what: 'Sail holds 2.4 days of research at the ceiling above its reserve (under 3).',
    numbers: { runway_days_at_ceiling: 2.4, runway_days_held: 5, research_usd_day: 9.6, ceiling_usd_day: 15, topup_usd: 112, card_date: '2026-10-05' },
    since: '2026-10-07T04:20:00Z', hours: '6.0', doing: 'The budget rule tapers research on Sail to what it holds.',
    owner_step: 'top up Sail: about $112.00 buys 7 more days of research at the ceiling (the taper starts 2026-10-05)',
  });
  assert.equal(runway.subject, 'LTCM: stalled: Sail research runway short');
  const lines = runway.text.split('\n');
  assert.ok(lines.includes('- topup_usd: 112'));
  assert.ok(lines.includes('How long: 6 hours, since 2026-10-07T04:20:00Z.'));
  assert.ok(lines.includes('Only you can do this: top up Sail: about $112.00 buys 7 more days of research at the ceiling (the taper starts 2026-10-05). The House keeps working around it meanwhile.'));
  assert.equal(runway.text.includes('Nothing here needs you'), false);
  // A step the House ended with its own full stop is not said with two.
  const deploy = composeNotice({ ...FACTS, cause: 'owner_deploy', owner_step: 'deploy main at abc123 yourself.' });
  assert.equal(deploy.subject, 'LTCM: stalled: an owner deploy is waiting');
  assert.ok(deploy.text.includes('Only you can do this: deploy main at abc123 yourself. The House keeps'));
});

test('every cause the House can name has its subject here, and no other cause is composed', () => {
  // The House's own list (league/ops/stall.py CAUSES): a cause added there must be worded here, not refused.
  const listed = /\nCAUSES = \(([^)]*)\)/.exec(STALL_SOURCE);
  assert.ok(listed, 'league/ops/stall.py names its causes in one tuple');
  const causes = [...listed[1].matchAll(/"([a-z_]+)"/g)].map(match => match[1]);
  assert.deepEqual(causes.sort(), Object.keys(STALL_CAUSES).sort());
  for (const cause of causes) {
    const message = composeNotice({ ...FACTS, cause });
    assert.equal(message.subject, `LTCM: stalled: ${STALL_CAUSES[cause]}`, cause);
  }
  for (const cause of ['', undefined, null, 'BIRTHS', 'births\nBcc: x', '__proto__', 'toString', 'funding']) {
    assert.equal(composeNotice({ ...FACTS, cause }), null, String(cause));
  }
});

test('the composer reads every fact notice_facts writes, and no fact it does not write', () => {
  const written = /\ndef notice_facts\([\s\S]*?\n    return \{([\s\S]*?)\}\n/.exec(STALL_SOURCE);
  assert.ok(written, 'league/ops/stall.py notice_facts returns its facts as one dict');
  const keys = [...written[1].matchAll(/"([a-z_]+)":/g)].map(match => match[1]).sort();
  assert.deepEqual(keys, Object.keys(FACTS).sort(), 'the fixture is the House\'s shape');
  const read = new Set();
  composeNotice(new Proxy(FACTS, { get: (facts, key) => (read.add(key), facts[key]) }));
  // `notice_id` is the router's (and the router keys a stall on its cause); `desk_name` is read for every kind.
  assert.deepEqual([...read].filter(key => key !== 'desk_name').sort(), keys.filter(key => key !== 'notice_id'));
});

test('a figure is echoed only as a decimal, a time, yes or no, or a short token; a name that is not a lower-case word is dropped; the House\'s text stays on its line', () => {
  const odd = composeNotice({
    ...FACTS,
    what: 'Line one\nBcc: someone@example.com\r\nline two',
    numbers: {
      count: 3, share: '0.25', flag: true, off: false, when: '2026-10-07', causes: 'research_budget,under_line', sha: 'a3f2a629bc01',
      none: null, words: 'the swarm said <b>hi</b>', inf: Infinity, nan: NaN, nested: { a: 1 }, list: [1], long: 'x'.repeat(81),
      'Bad Name': 1, 'bcc\nx': 2, __proto__x: 3,
    },
    hours: 'soon', since: 'yesterday', doing: 'a\u0000b\tc', owner_step: '   ', at: 'x'.repeat(60),
  });
  const lines = odd.text.split('\n');
  assert.equal(lines[0], 'Line one Bcc: someone@example.com line two');
  assert.deepEqual(lines.slice(2, 18), [
    'The numbers:', '- count: 3', '- share: 0.25', '- flag: yes', '- off: no', '- when: 2026-10-07', '- causes: research_budget,under_line',
    '- sha: a3f2a629bc01', '- none: unknown', '- words: unknown', '- inf: unknown', '- nan: unknown', '- nested: unknown',
    '- list: unknown', '- long: unknown', '',
  ]);
  for (const name of ['Bad Name', 'bcc', '__proto__']) assert.equal(odd.text.includes(name), false, name);
  assert.ok(lines.includes('How long: unknown.'));
  assert.ok(lines.includes('What the House is doing: a b c'));
  assert.ok(lines.includes(NONE_NEEDED), 'a blank step is no step');
  assert.ok(lines.includes(`At: ${'x'.repeat(40)}.`));
  for (const echoed of ['<b>', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.', 'Infinity', 'NaN', '[object']) {
    assert.equal(odd.text.includes(echoed), false, echoed);
  }
  // No figures, no sentence: the mail still says the cause and that nothing was given.
  const bare = composeNotice({ kind: 'stall', cause: 'gym_runs' });
  assert.deepEqual(bare.text.split('\n'), [
    'The floor is stalled: too few Gym runs.', '', 'How long: unknown.', 'What the House is doing: it did not say.', NONE_NEEDED,
    'At: an unknown time.', ...END,
  ]);
  // At most sixteen figures.
  const many = composeNotice({ ...FACTS, numbers: Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`n${i}`, i])) });
  assert.equal(many.text.split('\n').filter(line => line.startsWith('- n')).length, 16);
});

test('through /v1/notify: one mail per cause per 12 hours whatever id the House sends, another cause on its own, inside the day\'s cap', async () => {
  assert.equal(STALL_NOTICE_MS, 12 * HOUR);
  const gate = createGate({ store: memoryStore(), env: env(), now: () => NOW });
  const sent = [];
  const post = (facts, at, settings = {}) => route(new Request(`${GATEWAY}/v1/notify`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(facts),
  }), env(settings), { gate, now: () => at, mailer: async message => void sent.push(message) });
  const first = await (await post(FACTS, NOW)).json();
  assert.deepEqual([first.sent, first.subject], [true, 'LTCM: stalled: no births']);
  // The House retries, loses its own record, or sends another id for the same cause: one mail inside 12 hours.
  for (const [hours, id] of [[0.5, 'stall:births'], [6, 'stall:births:other'], [11.9, undefined]]) {
    const again = await (await post({ ...FACTS, notice_id: id }, NOW + hours * HOUR)).json();
    assert.equal(again.duplicate, true, `${hours} h later`);
  }
  assert.equal(sent.length, 1);
  // Another cause is its own.
  assert.equal((await (await post({ ...FACTS, cause: 'gym_runs', notice_id: 'stall:gym_runs' }, NOW + HOUR)).json()).sent, true);
  assert.equal(sent.length, 2);
  // Twelve hours on, the same cause is mailed again.
  assert.equal((await (await post(FACTS, NOW + 12 * HOUR)).json()).sent, true);
  assert.equal(sent.length, 3);
  // The day's cap holds for stalls too (here a cap of 1 on a day that has mailed already).
  const capped = await post({ ...FACTS, cause: 'validations' }, NOW + 12 * HOUR + 60000, { NOTIFY_MAX_PER_DAY: '1' });
  assert.equal(capped.status, 429);
  assert.equal(sent.length, 3);
  // A cause not named is refused before anything is counted or mailed.
  assert.equal((await post({ ...FACTS, cause: 'nonsense' }, NOW)).status, 400);
  assert.equal(sent.length, 3);
});
