// The funding notice (V3-A, WP8): the budget rule's card notice (league/ops/budget.py `notice_facts`) composed into one
// compact mail that names each figure (the rate the desk is held to now, the rate the rule wants; each runway as days
// above the meter's reserve), a drill marked as one, at most once per notice id for eight days, inside the day's notice
// cap.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { composeNotice, NOTICE_KINDS, FLOOR, CONSOLE } from '../lib/email.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-05T00:30:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const env = (extra = {}) => ({ GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', CAP_TIMEZONE: 'America/New_York', ...extra });

//: The facts as league/ops/budget.py `notice_facts` writes them (money as two-decimal strings, runway as one-decimal)
//: under the budget's rule version 2, for an example Sail prefund of 140 with 1.00 a day fixed (a round figure, never
//: the account's): research runs at its 15.00 share of the owner's ceiling, the meter holds 6.4 days of that above its
//: reserve (the Sail guard's own line, 37: under the 7-day card line), 112.00 buys 7 more, and the taper starts on the
//: card date (when 5 days are left). The amount and its days go out under rule version 1's names too (`restore_*`).
const FACTS = {
  kind: 'funding', notice_id: 'funding:sail:2026-W41:r2', meter: 'sail', balance_usd: '140.00', usd_day: '16.00', fixed_usd_day: '1.00',
  research_usd_day: '15.00', runway_days: '6.4', runs_out_on: '2026-10-11', current_usd_day: '16.00', current_research_usd_day: '15.00',
  current_runway_days: '6.4', topup_usd: '112.00', topup_days: 7, restore_usd: '112.00', restore_days: 7, card_line_days: 7,
  card_date: '2026-10-06', at: '2026-10-05T00:30:00Z', test: false,
};
const SUBJECT = 'LTCM: Sail runway 6.4 days at the rate the budget wants; add $112.00 by 2026-10-06';
const HOLDS = 'Sail holds $140.00.';
const HELD = 'The desk is held to $16.00 a day on it now (fixed $1.00, research up to $15.00); at that rate it lasts 6.4 days above its reserve.';
const WANTS = 'The budget rule wants $16.00 a day for it (fixed $1.00, research $15.00: its share of the research ceiling); at that rate it lasts 6.4 days above its reserve, to about 2026-10-11. That is the runway under the 7-day card line.';
const TOPUP = 'Adding $112.00 buys 7 more days at the rate the rule wants. Add it by 2026-10-06.';
const NOTHING_STOPS = 'Nothing stops if no card is added: research stays throttled to what Sail sustains.';
const NOT_SENT = 'What the desk is held to on it now was not sent: the figures below are at the rate the budget rule wants, not a spend the desk is making.';
const NO_PROMISE = 'If no card is added, research on Sail stays throttled; how long Sail lasts at the rate the desk is held to now was not sent.';
const lasts = (days, research) => `If no card is added, Sail lasts ${days} days above its reserve at the rate the desk is held to now: research on it ${research}.`;
const NONE_LEFT = 'Sail has no runway left above its reserve: research on it stays throttled until it is funded.';
const AT_ZERO = 'is already at $0.00, so there is nothing left to throttle';
const TAPERS = 'tapers as the balance falls';
const END = ['The budget rule never raises a cap or moves money.', 'At: 2026-10-05T00:30:00Z.', '', FLOOR, CONSOLE, ''];
const DRILL = 'THIS IS A DRILL: a synthetic cliff tests that this notice reaches you. Its figures are the drill\'s, not the desk\'s. Nothing needs doing.';
//: The line that says what happens with no card (the one before `END`).
const closing = facts => composeNotice(facts).text.split('\n').at(-END.length - 1);

test('a funding notice says what the meter holds, the rate the desk is held to on it now, what the rule wants, the days of research left at each above the reserve, the exact amount that buys seven more, and by when', () => {
  assert.ok(NOTICE_KINDS.includes('funding'));
  const message = composeNotice(FACTS);
  assert.equal(message.subject, SUBJECT);
  assert.deepEqual(message.text.split('\n'), [HOLDS, HELD, WANTS, TOPUP, lasts('6.4', TAPERS), ...END]);
  // What the rule wants is said as the meter's share of the research ceiling, and the amount as what buys more days:
  // no floor, no profit share and no days restored (the budget's rule version 1) are named.
  assert.equal(/floor|profit|restores/i.test(message.text), false);
  // Neither rate is worded as a spend: the current one is the rate the rule holds the desk to (its fixed cost plus the
  // day's research budget), a ceiling and no metered figure, and the wanted one is what the rule would give.
  assert.equal(/spen[dt]/i.test(message.text), false);
  assert.deepEqual(message.text.match(/held to \$[\d.]+/g), ['held to $16.00']);
  // Each runway is days until the meter's reserve, and is said as that wherever a count of days is.
  assert.deepEqual(message.text.match(/lasts [\d.]+ days( above its reserve)?/g), Array(3).fill('lasts 6.4 days above its reserve'));
  const claude = composeNotice({ ...FACTS, meter: 'claude', notice_id: 'funding:claude:2026-W41:r2' });
  assert.match(claude.subject, /^LTCM: Claude \(Anthropic\) runway 6\.4 days at the rate the budget wants;/);
  assert.match(claude.text, /^Claude \(Anthropic\) holds \$140\.00\.\n/);
  assert.ok(claude.text.includes('If no card is added, Claude (Anthropic) lasts 6.4 days above its reserve at the rate the desk is held to now: research on it tapers as the balance falls.'));
  // Tapered (the House's own pinned notice is below): the rate the desk is held to is under the one the rule wants.
  const tapered = composeNotice({ ...FACTS, balance_usd: '75.00', runway_days: '2.4', runs_out_on: '2026-10-07', current_usd_day: '7.60',
    current_research_usd_day: '6.60', current_runway_days: '5.0', card_date: '2026-10-05' });
  assert.deepEqual(tapered.text.match(/held to \$[\d.]+|wants \$[\d.]+/g), ['held to $7.60', 'wants $16.00']);
  assert.ok(tapered.text.includes(lasts('5', TAPERS)));
});

test('the composer reads every fact notice_facts writes, and no fact it does not write', () => {
  // The House's own list: a fact added or renamed there must be worded here, not ignored (the current rate once was).
  const source = readFileSync(new URL('../../league/ops/budget.py', import.meta.url), 'utf8');
  const written = /\ndef notice_facts\([\s\S]*?\n    return \{([\s\S]*?)\}\n/.exec(source);
  assert.ok(written, 'league/ops/budget.py notice_facts returns its facts as one dict');
  const keys = [...written[1].matchAll(/"([a-z_]+)":/g)].map(match => match[1]).sort();
  assert.deepEqual(keys, Object.keys(FACTS).sort(), 'the fixture is the House\'s shape');
  const read = new Set();
  composeNotice(new Proxy(FACTS, { get: (facts, key) => (read.add(key), facts[key]) }));
  // `notice_id` is the router's (the dedupe); `desk_name` is read for every kind and is no funding fact.
  assert.deepEqual([...read].filter(key => key !== 'desk_name').sort(), keys.filter(key => key !== 'notice_id'));
});

test('with no current rate sent, no current spend is claimed, the figures are said to be the rate the rule wants, and nothing is promised about what stops', () => {
  const { current_usd_day, current_research_usd_day, current_runway_days, ...older } = FACTS;
  // An older House sends none of them; a balance the rule could not read for research sends no total and no runway
  // (league/ops/budget.py: its research is 0.00); a total that is not a decimal is no total. How long the meter lasts at
  // the rate the desk is held to is then unknown here, so the mail does not say that nothing stops.
  for (const [name, facts] of [
    ['an older House', older],
    ['an unreadable balance', { ...FACTS, current_usd_day: null, current_research_usd_day: '0.00', current_runway_days: null }],
    ['a runway with no rate', { ...older, current_runway_days: '6.4' }],
    ['not a decimal', { ...FACTS, current_usd_day: '16.00\nBcc: x' }],
  ]) {
    const message = composeNotice(facts);
    assert.equal(message.subject, SUBJECT, name);
    assert.deepEqual(message.text.split('\n'), [HOLDS, NOT_SENT, WANTS, TOPUP, NO_PROMISE, ...END], name);
    assert.equal(/spend\w* \$/.test(message.text), false, name);
    assert.equal(message.text.includes('Nothing stops'), false, name);
  }
  // The unreadable balance as `notice_facts` writes it (the card line read from the gateway's own Sail reading): a
  // short runway at the wanted rate, and no word that nothing stops under it.
  const unread = composeNotice({ ...FACTS, balance_usd: '60.00', runway_days: '1.4', runs_out_on: '2026-10-06', current_usd_day: null,
    current_research_usd_day: '0.00', current_runway_days: null, card_date: '2026-10-05' });
  assert.equal(unread.subject, 'LTCM: Sail runway 1.4 days at the rate the budget wants; add $112.00 by 2026-10-05');
  assert.deepEqual(unread.text.split('\n'), [
    'Sail holds $60.00.', NOT_SENT,
    'The budget rule wants $16.00 a day for it (fixed $1.00, research $15.00: its share of the research ceiling); at that rate it lasts 1.4 days above its reserve, to about 2026-10-06. That is the runway under the 7-day card line.',
    'Adding $112.00 buys 7 more days at the rate the rule wants. Add it by 2026-10-05.',
    NO_PROMISE, ...END,
  ]);
});

test('nothing stops is said only while research is above zero and the runway at the rate the desk is held to is at or over the card line', () => {
  // The House's own pinned notice (league/tests/test_ops_budget.py, the short meter told once a week): Sail with 1.4
  // days of research left at the ceiling. The rule has tapered its research to 3.10 a day, which keeps 5 days above the
  // reserve at the rate it is held to: under the card line, so nothing is promised.
  const pinned = { ...FACTS, notice_id: 'funding:sail:2026-W43:r2', balance_usd: '60.00', usd_day: '16.50', fixed_usd_day: '1.50', runway_days: '1.4',
    runs_out_on: '2026-10-21', current_usd_day: '4.60', current_research_usd_day: '3.10', current_runway_days: '5.0', topup_usd: '115.50',
    restore_usd: '115.50', card_date: '2026-10-20', at: '2026-10-20T21:30:00Z' };
  const message = composeNotice(pinned);
  assert.equal(message.subject, 'LTCM: Sail runway 1.4 days at the rate the budget wants; add $115.50 by 2026-10-20');
  assert.deepEqual(message.text.split('\n'), [
    'Sail holds $60.00.',
    'The desk is held to $4.60 a day on it now (fixed $1.50, research up to $3.10); at that rate it lasts 5 days above its reserve.',
    'The budget rule wants $16.50 a day for it (fixed $1.50, research $15.00: its share of the research ceiling); at that rate it lasts 1.4 days above its reserve, to about 2026-10-21. That is the runway under the 7-day card line.',
    'Adding $115.50 buys 7 more days at the rate the rule wants. Add it by 2026-10-20.',
    'If no card is added, Sail lasts 5 days above its reserve at the rate the desk is held to now: research on it tapers as the balance falls.',
    'The budget rule never raises a cap or moves money.', 'At: 2026-10-20T21:30:00Z.', '', FLOOR, CONSOLE, '',
  ]);
  // Research at 0.00 is never told that nothing stops, days from the reserve or over the card line alike (a prefund left
  // with no card passes through every one of these, week by week).
  const idle = { current_usd_day: '1.00', current_research_usd_day: '0.00' };
  for (const [current_runway_days, said] of [['0.3', '0.3'], ['2.0', '2'], ['4.9', '4.9'], ['6.4', '6.4'], ['7.0', '7'], ['8.5', '8.5'], [9, '9']]) {
    assert.equal(closing({ ...FACTS, ...idle, current_runway_days }), lasts(said, AT_ZERO), said);
  }
  assert.equal(closing({ ...FACTS, ...idle, current_research_usd_day: 0, current_runway_days: '4.9' }), lasts('4.9', AT_ZERO));
  assert.equal(closing({ ...FACTS, meter: 'claude', current_usd_day: '0.00', current_research_usd_day: '0.00' }),
    'If no card is added, Claude (Anthropic) lasts 6.4 days above its reserve at the rate the desk is held to now: research on it is already at $0.00, so there is nothing left to throttle.');
  // Research above zero: with the runway at the rate the desk is held to at the card line or over it nothing stops;
  // under it (where the rule's own facts always are: a meter is told only while it holds fewer days than the line at the
  // ceiling, and the taper keeps fewer still) nothing is promised.
  for (const current_runway_days of ['7.0', 7, '7.1', '9.0']) assert.equal(closing({ ...FACTS, current_runway_days }), NOTHING_STOPS, String(current_runway_days));
  assert.equal(closing({ ...FACTS, current_usd_day: '8.00', current_research_usd_day: '7.00', current_runway_days: '7.0' }), NOTHING_STOPS);
  for (const [current_runway_days, said] of [['6.4', '6.4'], [6.49, '6.49'], ['5.0', '5'], ['0.1', '0.1']]) {
    assert.equal(closing({ ...FACTS, current_runway_days }), lasts(said, TAPERS), said);
  }
  // A card line or a research figure that does not read shows nothing; a line over the runway is a line it is under.
  for (const odd of [{ card_line_days: null }, { card_line_days: 'seven' }, { card_line_days: 120 }, { current_research_usd_day: null }, { current_research_usd_day: '<b>' }]) {
    assert.equal(closing({ ...FACTS, current_runway_days: '9.0', ...odd }), lasts('9', TAPERS), JSON.stringify(odd));
  }
  // Every combination of the figures it is read from: said exactly when each of them shows it, and never otherwise.
  let said = 0;
  for (const current_usd_day of [undefined, null, 'x', '16.00']) {
    for (const current_research_usd_day of [undefined, null, 'x', '-0.50', '0.00', 0, '0.01', 15]) {
      for (const current_runway_days of [undefined, null, 'soon', '0.0', '0.3', '6.4', '7.0', 9]) {
        for (const card_line_days of [undefined, null, 'x', 7, '7']) {
          for (const runway_days of ['0.0', '6.4']) {
            const facts = { ...FACTS, current_usd_day, current_research_usd_day, current_runway_days, card_line_days, runway_days };
            const shown = current_usd_day === '16.00' && ['0.01', 15].includes(current_research_usd_day)
              && ['7.0', 9].includes(current_runway_days) && [7, '7'].includes(card_line_days) && runway_days === '6.4';
            assert.equal(composeNotice(facts).text.includes('Nothing stops'), shown, JSON.stringify(facts));
            assert.equal(closing(facts) === NOTHING_STOPS, shown, JSON.stringify(facts));
            said += shown ? 1 : 0;
          }
        }
      }
    }
  }
  assert.equal(said, 8);
});

test('a current rate with no runway says so; a meter with no runway left is not told that nothing stops; the mail states one outcome', () => {
  for (const current_runway_days of [null, undefined, 'soon']) {
    assert.deepEqual(composeNotice({ ...FACTS, current_runway_days }).text.split('\n'), [
      HOLDS, 'The desk is held to $16.00 a day on it now (fixed $1.00, research up to $15.00); the House sent no runway at that rate.', WANTS,
      TOPUP, NO_PROMISE, ...END,
    ]);
  }
  // Claude under its reserve, as `notice_facts` writes it: nothing is sustained, at either rate. The amount is what the
  // meter lacks to its reserve and seven days at the ceiling above it.
  const empty = { ...FACTS, meter: 'claude', balance_usd: '3.00', usd_day: '10.00', fixed_usd_day: '0.00', research_usd_day: '10.00',
    runway_days: '0.0', runs_out_on: '2026-10-05', current_usd_day: '0.00', current_research_usd_day: '0.00', current_runway_days: '0.0', topup_usd: '72.00',
    restore_usd: '72.00', card_date: '2026-10-05' };
  const message = composeNotice(empty);
  assert.equal(message.subject, 'LTCM: Claude (Anthropic) runway 0 days at the rate the budget wants; add $72.00 by 2026-10-05');
  assert.deepEqual(message.text.split('\n'), [
    'Claude (Anthropic) holds $3.00.',
    'The desk is held to $0.00 a day on it now (fixed $0.00, research up to $0.00); at that rate it lasts 0 days above its reserve.',
    'The budget rule wants $10.00 a day for it (fixed $0.00, research $10.00: its share of the research ceiling); at that rate it lasts 0 days above its reserve, to about 2026-10-05. That is the runway under the 7-day card line.',
    'Adding $72.00 buys 7 more days at the rate the rule wants. Add it by 2026-10-05.',
    'Claude (Anthropic) has no runway left above its reserve: research on it stays throttled until it is funded.',
    ...END,
  ]);
  // The closing sentence is read from the runway at the rate the desk is held to when one was sent (with its rate), and
  // from the wanted rate's only when none was. A runway of zero there reads as none left, and nothing stops is never said.
  for (const facts of [{ ...FACTS, current_runway_days: 0 }, { ...FACTS, current_runway_days: '0.0', runway_days: '0.0' },
    { ...FACTS, current_usd_day: null, runway_days: '0.0' }, { ...FACTS, current_runway_days: null, runway_days: '0.0' }]) {
    assert.equal(composeNotice(facts).text.includes('Nothing stops'), false);
    assert.equal(closing(facts), NONE_LEFT, JSON.stringify(facts));
  }
  // Only the wanted runway at zero (a meter cents above its reserve, where the wanted rate's days round to 0.0 and the
  // held rate's do not): the mail has said how long the meter lasts at the held rate, so it does not also say that it has
  // none left, and it does not say that nothing stops.
  for (const [over, said] of [
    [{}, lasts('6.4', TAPERS)],
    [{ current_usd_day: '1.00', current_research_usd_day: '0.00', current_runway_days: '0.1' }, lasts('0.1', AT_ZERO)],
  ]) {
    const facts = { ...FACTS, ...over, runway_days: '0.0' };
    const text = composeNotice(facts).text;
    assert.equal(closing(facts), said, JSON.stringify(over));
    assert.equal(text.includes('Nothing stops'), false, JSON.stringify(over));
    assert.equal(text.includes('has no runway left'), false, JSON.stringify(over));
  }
  // Over every combination of the two runways and the current rate: a mail that says the meter lasts some days at the
  // held rate never says it has none left, and one that says none is left never says it lasts a day at that rate.
  for (const current_usd_day of [undefined, null, '16.00']) {
    for (const current_runway_days of [undefined, null, '0.0', 0, '0.3', '6.4', '9.0']) {
      for (const runway_days of [undefined, null, '0.0', 0, '1.9', '6.4']) {
        const facts = { ...FACTS, current_usd_day, current_runway_days, runway_days };
        const text = composeNotice(facts).text;
        const held = /at that rate it lasts ([\d.]+) days above its reserve\.\n/.exec(text);
        const none = text.includes(NONE_LEFT);
        assert.equal(none && held !== null && Number(held[1]) > 0, false, JSON.stringify(facts));
        assert.equal(none && /If no card is added/.test(text), false, JSON.stringify(facts));
        assert.equal(none, current_usd_day === '16.00' && current_runway_days !== undefined && current_runway_days !== null
          ? Number(current_runway_days) === 0 : Number(runway_days) === 0 && runway_days !== null && runway_days !== undefined, JSON.stringify(facts));
      }
    }
  }
  // A runway with no rate is not read: the meter is not said to have none left, and nothing is promised either.
  assert.deepEqual(composeNotice({ ...FACTS, current_usd_day: null, current_runway_days: '0.0' }).text.split('\n'),
    [HOLDS, NOT_SENT, WANTS, TOPUP, NO_PROMISE, ...END]);
});

test('a drill says it is one; a meter not named is refused; a figure that is not a decimal is never echoed', () => {
  const drill = composeNotice({ ...FACTS, test: true, notice_id: 'funding-test:sail:2026-W41' });
  assert.equal(drill.subject, SUBJECT.replace(/^LTCM/, 'LTCM [drill]'));
  assert.deepEqual(drill.text.split('\n'), [DRILL, HOLDS, HELD, WANTS, TOPUP, lasts('6.4', TAPERS), ...END]);
  // Only `true` is a drill, and nothing but a drill is marked as one.
  for (const flag of [false, undefined, null, 'true', 1]) {
    const real = composeNotice({ ...FACTS, test: flag });
    assert.equal(real.subject, SUBJECT, String(flag));
    assert.equal(/drill/i.test(real.text), false, String(flag));
  }
  for (const meter of ['openai', 'SAIL', '', undefined, 'sail\nBcc: x', '__proto__', 'toString']) {
    assert.equal(composeNotice({ ...FACTS, meter }), null, String(meter));
  }
  const odd = composeNotice({
    ...FACTS, balance_usd: '1e9<script>', topup_usd: '112<b>', restore_usd: null, runway_days: 'soon', card_date: 'tomorrow\nBcc: x',
    at: 'x'.repeat(100), usd_day: '16.00; DROP', fixed_usd_day: {}, research_usd_day: [15], runs_out_on: '2026-10-11\nBcc: x',
    current_usd_day: 16, current_research_usd_day: '<b>', current_runway_days: Infinity, topup_days: '7 days', restore_days: NaN,
    card_line_days: NaN,
  });
  assert.equal(odd.subject, 'LTCM: Sail runway unknown days at the rate the budget wants; add unknown by unknown');
  assert.deepEqual(odd.text.split('\n').slice(0, 5), [
    'Sail holds unknown.',
    'The desk is held to $16.00 a day on it now (fixed unknown, research up to unknown); the House sent no runway at that rate.',
    'The budget rule wants unknown a day for it (fixed unknown, research unknown: its share of the research ceiling); at that rate it lasts unknown days above its reserve, to about unknown. That is the runway under the unknown-day card line.',
    'Adding unknown buys unknown more days at the rate the rule wants. Add it by unknown.',
    NO_PROMISE,
  ]);
  for (const echoed of ['<script>', '<b>', 'Bcc', 'DROP', 'Infinity', 'NaN', '[object', 'x'.repeat(41)]) assert.equal(odd.text.includes(echoed), false, echoed);
  // Numbers as numbers read as well as numbers as strings.
  const numbers = composeNotice({ ...FACTS, balance_usd: 140, usd_day: 16, fixed_usd_day: 1, research_usd_day: 15, runway_days: 6.4,
    current_usd_day: 16, current_research_usd_day: 15, current_runway_days: 6.4, topup_usd: 112, topup_days: '7', restore_usd: 112,
    restore_days: '7', card_line_days: '7' });
  assert.deepEqual(numbers, composeNotice(FACTS));
});

test('a House and a gateway on different rule versions never mail an amount that could not be read', () => {
  // THIS gateway, a House still on rule version 1 (the gateway deploys first, and a House rollback does not take it
  // back): the facts name the amount `restore_usd`/`restore_days` only, with that rule's figures (a research floor plus
  // a profit share, a 60-day card line, what restores 90 days). The mail is that rule's own, word for word.
  const one = {
    kind: 'funding', notice_id: 'funding:sail:2026-W41', meter: 'sail', balance_usd: '200.00', usd_day: '4.00', fixed_usd_day: '1.00',
    research_usd_day: '3.00', runway_days: '47.5', runs_out_on: '2026-11-21', current_usd_day: '2.11', current_research_usd_day: '1.11',
    current_runway_days: '90.0', restore_usd: '170.00', restore_days: 90, card_line_days: 60, card_date: '2026-10-05',
    at: '2026-10-05T00:30:00Z', test: false,
  };
  const old = composeNotice(one);
  assert.equal(old.subject, 'LTCM: Sail runway 47.5 days at the rate the budget wants; add $170.00 by 2026-10-05');
  assert.deepEqual(old.text.split('\n'), [
    'Sail holds $200.00.',
    'The desk is held to $2.11 a day on it now (fixed $1.00, research up to $1.11); at that rate it lasts 90 days above its reserve.',
    'The budget rule wants $4.00 a day for it (fixed $1.00, research $3.00: the research floor plus what profit earned); at that rate it lasts 47.5 days above its reserve, to about 2026-11-21. That is the runway under the 60-day card line.',
    'Adding $170.00 restores 90 days of runway at the rate the rule wants. Add it by 2026-10-05.',
    NOTHING_STOPS, ...END,
  ]);
  assert.equal(closing({ ...one, current_runway_days: '30.0' }),
    'If no card is added, Sail lasts 30 days above its reserve at the rate the desk is held to now: research on it stays throttled.');
  assert.equal(/unknown|ceiling|buys|tapers/.test(old.subject + old.text), false);
  // A House on rule version 2, an OLDER gateway (it reads `restore_*` only): the House sends the same amount and days
  // under both names (league/tests/test_ops_budget.py pins that `notice_facts` writes them equal), so that composer
  // finds its amount. Here the new names decide: the old ones change no word, present, absent or different.
  assert.deepEqual([FACTS.restore_usd, FACTS.restore_days], [FACTS.topup_usd, FACTS.topup_days]);
  const { restore_usd, restore_days, ...newNames } = FACTS;
  for (const facts of [newNames, { ...FACTS, restore_usd: null, restore_days: null }, { ...FACTS, restore_usd: '999.00', restore_days: 90 }]) {
    assert.deepEqual(composeNotice(facts), composeNotice(FACTS));
  }
  assert.ok(composeNotice(FACTS).text.includes(TOPUP));
  // Neither name: nothing is known, and the mail says so rather than borrow a figure.
  const neither = composeNotice({ ...newNames, topup_usd: undefined, topup_days: undefined });
  assert.match(neither.subject, /; add unknown by 2026-10-06$/);
  assert.ok(neither.text.includes('Adding unknown buys unknown more days at the rate the rule wants.'));
});

test('through /v1/notify: mailed once per notice id for eight days, counted against the day\'s cap like any notice', async () => {
  const gate = createGate({ store: memoryStore(), env: env(), now: () => NOW });
  const sent = [];
  const post = (facts, at, settings = {}) => route(new Request(`${GATEWAY}/v1/notify`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(facts),
  }), env(settings), { gate, now: () => at, mailer: async message => void sent.push(message) });
  const first = await (await post(FACTS, NOW)).json();
  assert.equal(first.sent, true);
  assert.equal(first.subject, SUBJECT);
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
  const capped = await post({ ...FACTS, notice_id: 'funding:claude:2026-W41:r2', meter: 'claude' }, later, { NOTIFY_MAX_PER_DAY: '1' });
  assert.equal(capped.status, 429);
  assert.equal(sent.length, 4);
  assert.equal((await post({ ...FACTS, meter: 'openai', notice_id: 'funding:openai:2026-W41:r2' }, NOW)).status, 400);
});
