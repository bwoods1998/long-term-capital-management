import test from 'node:test';
import assert from 'node:assert/strict';
import { createGate, TYPESAFE_KEY } from '../lib/gate.mjs';
import { route } from '../lib/router.mjs';
import { MODEL, MAX_CALLS, actualCost, validAnswers, admit } from '../lib/typesafe.mjs';
import { memoryStore, recorder, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-09-21T01:00:00Z');
const settings = { GATEWAY_TOKEN: TOKEN, TYPE_SAFE_TOKEN: 'typesafe-test-secret',
  TYPESAFE_PILOT_USD: '1', TYPESAFE_PILOT_END: '2026-09-22T20:22:14.430Z' };
const body = { model: MODEL, state: { error: 'Missing observations for BNB/USD; BTC/USD has bars.' },
  questions: { route: { type: 'choice', instructions: 'Which operation addresses the stated missing input?',
    criteria: { narrow: 'Use an available symbol', repeat: 'Repeat the unchanged request' } } } };
const answer = { model: MODEL, answers: { route: { type: 'choice', choice: 'narrow',
  probabilities: { narrow: .95, repeat: .05 }, confidence: .9 } }, usage: { input_tokens: 1000, output_tokens: 40 } };

const request = (id = 'pilot:1', payload = body, token = TOKEN) => new Request('https://gateway.test/v1/typesafe/systemone', {
  method: 'POST', headers: { Authorization: `Bearer ${token}`, 'X-LTCM-Request': id }, body: JSON.stringify(payload),
});
function setup(env = settings, reply = { body: JSON.stringify(answer) }, store = memoryStore()) {
  const gate = createGate({ store, env, now: () => NOW });
  const tape = recorder(reply);
  return { gate, store, tape, call: r => route(r, env, { gate, fetcher: tape.fetcher, now: () => NOW }) };
}

test('Jev keeps provider credentials at the gateway and reports precise metered cost', async () => {
  const x = setup();
  const res = await x.call(request());
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('X-LTCM-Cost-USD'), '0.000042');
  assert.equal(res.headers.get('X-LTCM-Cost-Known'), 'true');
  assert.deepEqual(await res.json(), answer);
  assert.equal(x.tape.calls[0].url, 'https://api.typesafe.ai/v1/systemone');
  assert.equal(x.tape.calls[0].headers.Authorization, 'Bearer typesafe-test-secret');
  assert.equal(x.tape.calls[0].redirect, 'manual');
  assert.equal(x.gate.status().typesafe.spent_usd, '0.000042');
  assert.equal(x.gate.status().today.orders, 0);
  assert.equal(x.gate.status().frontier.calls, 0);
});

test('unauthorized, unconfigured, unpriced and oversized calls never reach the provider', async () => {
  const x = setup();
  assert.equal((await x.call(request('a', body, 'wrong'))).status, 401);
  assert.equal((await setup({ ...settings, TYPE_SAFE_TOKEN: undefined }).call(request())).status, 503);
  assert.equal((await x.call(request('b', { ...body, model: 'jev-latest' }))).status, 400);
  assert.equal((await x.call(request('c', { ...body, state: 'a'.repeat(65536) }))).status, 413);
  assert.equal((await x.call(request('bad request identity'))).status, 400);
  assert.equal(x.tape.calls.length, 0);
});

test('pilot is explicitly enabled, expires, and never renews at a calendar boundary', async () => {
  for (const env of [{ ...settings, TYPESAFE_PILOT_USD: undefined },
    { ...settings, TYPESAFE_PILOT_END: undefined }, { ...settings, TYPESAFE_PILOT_END: '2026-09-20' }]) {
    const x = setup(env); assert.equal((await x.call(request())).status, 402); assert.equal(x.tape.calls.length, 0);
  }
  const store = memoryStore({ [TYPESAFE_KEY]: JSON.stringify({ spent: '1000000', calls: 2, pending: 0, breaches: 0 }) });
  const x = setup({ ...settings, TYPESAFE_PILOT_END: '2027-01-01' }, undefined, store);
  assert.equal(x.gate.typesafeReserve({ id: 'next-month', digest: 'a'.repeat(64), at: Date.parse('2026-10-01') }).status, 402);
});

test('concurrent calls cannot spend the same final allowance', async () => {
  const x = setup({ ...settings, TYPESAFE_PILOT_USD: '0.01' }, new Error('timeout'));
  const replies = await Promise.all([x.call(request('one')), x.call(request('two'))]);
  assert.deepEqual(replies.map(r => r.status).sort(), [402, 502]);
  assert.equal(x.tape.calls.length, 1);
  assert.equal(x.gate.typesafeStatus().spent_usd, '0.010000');
});

test('accepted request identities survive restart and cannot be rebilled or changed', async () => {
  const x = setup();
  await x.call(request());
  const restarted = setup(settings, undefined, x.store);
  assert.equal((await restarted.call(request())).status, 409);
  assert.equal((await restarted.call(request('pilot:1', { ...body, state: 'changed' }))).status, 409);
  assert.equal(restarted.tape.calls.length, 0);
  assert.equal(restarted.gate.typesafeSettle({ id: 'pilot:1', actual: '0' }).ok, false);
  assert.equal(restarted.gate.typesafeStatus().spent_usd, '0.000042');
});

test('ambiguous, malformed and provider-refused requests retain a full reservation', async () => {
  for (const reply of [new Error('transport failed'), { body: '{bad' }, { status: 401, body: '{"error":"secret diagnostics"}' },
    { body: JSON.stringify({ ...answer, usage: undefined }) }, { body: 'a'.repeat(128*1024+1) }]) {
    const x = setup(settings, reply);
    const res = await x.call(request());
    assert.equal(x.gate.typesafeStatus().spent_usd, '0.010000');
    assert.equal((await x.call(request())).status, 409);
    assert.equal(x.tape.calls.length, 1);
    assert.doesNotMatch(await res.text(), /secret diagnostics/);
  }
});

test('typed but incompatible answers are rejected after accounting for their cost', async () => {
  const bad = structuredClone(answer); bad.answers.route.probabilities.narrow = .7;
  const x = setup(settings, { body: JSON.stringify(bad) });
  assert.equal((await x.call(request())).status, 502);
  assert.equal(x.gate.typesafeStatus().spent_usd, '0.000042');
});

test('a pricing breach records the charge and closes future admission', async () => {
  const x = setup(settings, { body: JSON.stringify({ ...answer, usage: { input_tokens: 1000000 } }) });
  await x.call(request());
  assert.equal(x.gate.typesafeStatus().spent_usd, '0.042000');
  assert.equal(x.gate.typesafeStatus().breaches, 1);
  assert.equal((await x.call(request('second'))).status, 402);
  assert.equal(x.tape.calls.length, 1);
});

test('the lifetime call count remains bounded even when provider usage is zero', () => {
  const store = memoryStore({ [TYPESAFE_KEY]: JSON.stringify({ spent: '0', calls: MAX_CALLS-1, pending: 0, breaches: 0 }) });
  const gate = setup(settings, undefined, store).gate;
  assert.equal(gate.typesafeReserve({ id: 'last', digest: 'a'.repeat(64) }).ok, true);
  assert.equal(gate.typesafeSettle({ id: 'last', actual: '0' }).ok, true);
  assert.equal(gate.typesafeReserve({ id: 'over', digest: 'b'.repeat(64) }).status, 402);
});

test('explicit persistent mode resumes unused allowance without resetting costs, identities or holds', async () => {
  const x = setup(settings, new Error('uncertain upstream response'));
  await x.call(request('old-unknown'));
  const env = { ...settings, TYPESAFE_PERSISTENT: 'true', TYPESAFE_PILOT_END: '2020-01-01' };
  const resumed = setup(env, undefined, x.store);
  assert.equal(resumed.gate.typesafeStatus().spent_usd, '0.010000');
  assert.equal(resumed.gate.typesafeStatus().ends, null);
  assert.equal(resumed.gate.typesafeStatus().persistent, true);
  assert.equal((await resumed.call(request('old-unknown'))).status, 409);
  assert.equal((await resumed.call(request('new-funded-request'))).status, 200);
  assert.equal(resumed.gate.typesafeStatus().spent_usd, '0.010042');
  const exhausted = setup({ ...env, TYPESAFE_PILOT_USD: '0.01' }, undefined, x.store);
  assert.equal((await exhausted.call(request('cannot-refill'))).status, 402);
  const revoked = setup({ ...env, TYPESAFE_PERSISTENT: 'false' }, undefined, x.store);
  assert.equal((await revoked.call(request('expired-again'))).status, 402);
  assert.equal(revoked.tape.calls.length, 0);
});

test('persistent mode requires literal configuration and still respects pricing breaches', () => {
  for (const setting of [undefined, true, 'yes', '1', 'TRUE']) {
    const gate = setup({ ...settings, TYPESAFE_PILOT_END: '2020-01-01', TYPESAFE_PERSISTENT: setting }).gate;
    assert.equal(gate.typesafeReserve({ id: 'closed', digest: 'a'.repeat(64) }).status, 402);
  }
  const store = memoryStore({ [TYPESAFE_KEY]: JSON.stringify({ spent: '100', calls: 1, pending: 0, breaches: 1 }) });
  const gate = setup({ ...settings, TYPESAFE_PERSISTENT: 'true' }, undefined, store).gate;
  assert.equal(gate.typesafeReserve({ id: 'breached', digest: 'a'.repeat(64) }).status, 402);
});

test('question schema cannot smuggle unpriced model settings or arbitrary result types', () => {
  assert.equal(admit(body), null);
  for (const bad of [{ ...body, endpoint: 'https://elsewhere.test' }, { ...body, stream: true },
    { ...body, questions: {} }, { ...body, questions: { q: { type: 'generation', instructions: 'Write code' } } },
    { ...body, questions: { q: { type: 'choice', instructions: 'Pick', criteria: { one: 'one' } } } }]) assert.ok(admit(bad));
  const noul = { ...body, questions: { q: { type: 'noul', instructions: 'Does the state show missing data?' } } };
  assert.equal(admit(noul), null);
  assert.equal(validAnswers(noul, { model: MODEL, answers: { q: { type: 'noul', noul: .5 } } }), true);
  assert.equal(validAnswers(noul, { model: MODEL, answers: { q: { type: 'noul', noul: 2 } } }), false);
  for (const usage of [undefined, {}, { input_tokens: -1 }, { input_tokens: '1000' }, { input_tokens: 1.5 }]) {
    assert.equal(actualCost(usage), null);
  }
  assert.equal(actualCost({ input_tokens: 1 }), 1n);
});

test('score questions are admitted as 2 to 10 ordered levels and their answers are checked', async () => {
  const rubric = { model: MODEL, state: { note: 'An 8-K withdrew full-year guidance.' },
    questions: { severity: { type: 'score', instructions: 'How material is this filing to the stock?',
      criteria: ['Routine', 'Notable', 'Material'] } } };
  const scored = { model: MODEL, answers: { severity: { type: 'score', score: 1.9, legend: { 0: 'Routine', 1: 'Notable', 2: 'Material' },
    probabilities: { 0: 0.0, 1: 0.1, 2: 0.9 }, confidence: 0.88 } }, usage: { input_tokens: 300, output_tokens: 12 } };
  assert.equal(admit(rubric), null);
  assert.match(admit({ ...rubric, questions: { s: { ...rubric.questions.severity, criteria: ['Only one'] } } }), /2 to 10/);
  assert.match(admit({ ...rubric, questions: { s: { ...rubric.questions.severity, criteria: Array(11).fill('level') } } }), /2 to 10/);
  assert.match(admit({ ...rubric, questions: { s: { ...rubric.questions.severity, criteria: { a: 'not ordered' } } } }), /2 to 10/);
  assert.match(admit({ ...rubric, questions: { s: { ...rubric.questions.severity, criteria: ['Fine', ' '] } } }), /2 to 10/);
  assert.match(admit({ ...rubric, questions: { s: { type: 'number', instructions: 'How many?' } } }), /choice, noul or score/);
  assert.equal(validAnswers(rubric, scored), true);
  for (const change of [
    a => { a.score = 2.5; },                                   // outside [0, n-1]
    a => { a.score = 0.4; },                                   // not the probability-weighted level
    a => { a.probabilities[2] = 0.5; },                        // does not sum to 1
    a => { delete a.probabilities[1]; a.probabilities[2] = 1; a.score = 2; },  // a level missing
    a => { a.probabilities[3] = 0; },                          // a level that was not asked
    a => { a.confidence = 1.2; },
    a => { a.type = 'noul'; },
  ]) {
    const bad = structuredClone(scored); change(bad.answers.severity);
    assert.equal(validAnswers(rubric, bad), false);
  }
  const x = setup(settings, { body: JSON.stringify(scored) });
  const res = await x.call(request('score:1', rubric));
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), scored);
});

test('the lifetime Jev line is set at or below funded money', async () => {
  const { readFile } = await import('node:fs/promises');
  const config = await readFile(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const cap = Number(config.match(/"TYPESAFE_PILOT_USD":\s*"([0-9.]+)"/)[1]);
  // Sept 25, 2026: $16.23 metered + the owner's ~$25 funded = $41.23.
  assert.ok(cap <= 41.23, `TYPESAFE_PILOT_USD ${cap} is above funded money`);
});
