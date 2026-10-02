// The funding notice (V3-A, WP8): the budget rule's card notice (league/ops/budget.py `notice_facts`) composed into one
// compact mail, a drill marked as one, at most once per notice id for eight days, inside the day's notice cap.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { composeNotice, NOTICE_KINDS } from '../lib/email.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-05T00:30:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const env = (extra = {}) => ({ GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', CAP_TIMEZONE: 'America/New_York', ...extra });

//: The facts as league/ops/budget.py `notice_facts` writes them: money as two-decimal strings, runway as one-decimal.
const FACTS = {
  kind: 'funding', notice_id: 'funding:sail:2026-W41', meter: 'sail', balance_usd: '84.20', usd_day: '1.62', fixed_usd_day: '1.12',
  research_usd_day: '0.50', runway_days: '51.9', restore_usd: '61.60', restore_days: 90, card_line_days: 60,
  card_date: '2026-10-05', runs_out_on: '2026-11-25', at: '2026-10-05T00:30:00Z', test: false,
};

test('a funding notice says the meter, the balance, the rate, the runway, the exact amount that restores it, and by when', () => {
  assert.ok(NOTICE_KINDS.includes('funding'));
  const message = composeNotice(FACTS);
  assert.equal(message.subject, 'LTCM: Sail runway 51.9 days; add $61.60 by 2026-10-05');
  assert.equal(message.text.split('\n').slice(0, 6).join('\n'), [
    'Sail balance: $84.20, spending $1.62 a day (fixed $1.12, research $0.50).',
    'Runway at that rate: 51.9 days (runs out about 2026-11-25); the card line is 60 days.',
    'Adding $61.60 restores 90 days of runway. Add it by 2026-10-05.',
    'The research budget already throttles itself toward the floor; it never raises a cap or moves money.',
    'At: 2026-10-05T00:30:00Z.',
    '',
  ].join('\n'));
  const claude = composeNotice({ ...FACTS, meter: 'claude', notice_id: 'funding:claude:2026-W41' });
  assert.match(claude.subject, /^LTCM: Claude \(Anthropic\) runway/);
});

test('a drill says it is one; a meter not named is refused; a figure that is not a decimal is never echoed', () => {
  const drill = composeNotice({ ...FACTS, test: true, notice_id: 'funding-test:sail:2026-W41' });
  assert.match(drill.subject, /^LTCM \[drill\]: Sail runway/);
  assert.match(drill.text, /^THIS IS A DRILL: a synthetic cliff tests that this notice reaches you\. Nothing needs doing\.\n/);
  for (const meter of ['openai', 'SAIL', '', undefined, 'sail\nBcc: x', '__proto__', 'toString']) {
    assert.equal(composeNotice({ ...FACTS, meter }), null, String(meter));
  }
  const odd = composeNotice({ ...FACTS, balance_usd: '1e9<script>', restore_usd: null, runway_days: 'soon', card_date: 'tomorrow\nBcc: x', at: 'x'.repeat(100) });
  assert.equal(odd.subject, 'LTCM: Sail runway unknown days; add unknown by unknown');
  assert.match(odd.text, /^Sail balance: unknown, spending \$1\.62/);
  assert.equal(odd.text.includes('<script>'), false);
  assert.equal(odd.text.includes('Bcc'), false);
  // Numbers as numbers read as well as numbers as strings.
  assert.equal(composeNotice({ ...FACTS, restore_usd: 61.6, runway_days: 51.9 }).subject, 'LTCM: Sail runway 51.9 days; add $61.60 by 2026-10-05');
});

test('through /v1/notify: mailed once per notice id for eight days, counted against the day\'s cap like any notice', async () => {
  const gate = createGate({ store: memoryStore(), env: env(), now: () => NOW });
  const sent = [];
  const post = (facts, at, settings = {}) => route(new Request(`${GATEWAY}/v1/notify`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(facts),
  }), env(settings), { gate, now: () => at, mailer: async message => void sent.push(message) });
  const first = await (await post(FACTS, NOW)).json();
  assert.equal(first.sent, true);
  assert.equal(first.subject, 'LTCM: Sail runway 51.9 days; add $61.60 by 2026-10-05');
  // The House retries, or a second instance sends the same week's notice, days later: one mail.
  for (const days of [1, 3, 6.9]) {
    const again = await (await post(FACTS, NOW + days * 86400000)).json();
    assert.equal(again.duplicate, true, `${days} days later`);
  }
  assert.equal(sent.length, 1);
  // Past eight days the id is forgotten (by then the House's ISO week has moved on anyway).
  assert.equal((await (await post(FACTS, NOW + 8.5 * 86400000)).json()).sent, true);
  assert.equal(sent.length, 2);
  // Other notices keep their 48 hours.
  const trade = { kind: 'test', notice_id: 'notice:one' };
  await post(trade, NOW);
  assert.equal((await (await post(trade, NOW + 47 * 3600000)).json()).duplicate, true);
  assert.equal((await (await post(trade, NOW + 49 * 3600000)).json()).sent, true);
  // The day's cap holds for funding notices too (the counter is the latest day's: here, 49 hours on).
  const later = NOW + 49 * 3600000;
  const capped = await post({ ...FACTS, notice_id: 'funding:claude:2026-W41', meter: 'claude' }, later, { NOTIFY_MAX_PER_DAY: '1' });
  assert.equal(capped.status, 429);
  assert.equal(sent.length, 4);
  assert.equal((await post({ ...FACTS, meter: 'openai', notice_id: 'funding:openai:2026-W41' }, NOW)).status, 400);
});
