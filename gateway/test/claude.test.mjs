// Claude through the gateway (Sept 26, 2026, the swarm sprint's B3): the route, its admission, the funded meter and the
// kill switch. No network: the fetcher stands in for Anthropic, and the gate runs on a memory store.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { priceTable, actualCost, worstCase, admit, capMicro, MAX_TOKENS } from '../lib/claude.mjs';
import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { formatUsdMicro } from '../lib/money.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const KEY = 'anthropic-test-key-never-leaves-the-worker';
const OPUS = { input: 4, cache_write: 5, cache_read: 0.2, output: 20 };
const SONNET = { input: 2, cache_write: 2.5, cache_read: 0.2, output: 10 };
const MODELS = JSON.stringify({ 'claude-opus-5-5': OPUS, 'claude-sonnet-5': SONNET });
const settings = extra => ({ GATEWAY_TOKEN: TOKEN, CLAUDE_API_KEY: KEY, CLAUDE_USD: '100', CLAUDE_MODELS: MODELS, ...extra });
const NOW = Date.parse('2026-09-27T14:00:00Z');

const body = (extra = {}) => ({
  model: 'claude-opus-5-5', max_tokens: 16000, thinking: { type: 'adaptive' }, output_config: { effort: 'high' },
  system: [{ type: 'text', text: 'You diagnose option-trading programs.', cache_control: { type: 'ephemeral' } }],
  messages: [{ role: 'user', content: 'The family, its program and its Train diagnostics.' }], ...extra,
});
const USAGE = { input_tokens: 2000, cache_creation_input_tokens: 10000, cache_read_input_tokens: 30000, output_tokens: 6000 };
const message = (extra = {}) => ({ id: 'msg_1', type: 'message', role: 'assistant', model: 'claude-opus-5-5',
  content: [{ type: 'thinking', thinking: '' }, { type: 'text', text: '{"decision":"retire"}' }], stop_reason: 'end_turn', usage: USAGE, ...extra });

const ask = (payload, headers = {}, path = '/v1/claude/messages', method = 'POST') => new Request(`https://gw${path}`, {
  method, ...(method === 'POST' ? { body: typeof payload === 'string' ? payload : JSON.stringify(payload) } : {}),
  headers: { Authorization: `Bearer ${TOKEN}`, ...headers },
});

/** One call through the front door: the answer, what Anthropic received, what the gate held meanwhile, and its meter after. */
async function call(payload, answer, { env = settings(), gate = null, headers = {} } = {}) {
  gate = gate || createGate({ store: memoryStore(), env, now: () => NOW });
  const seen = [];
  const fetcher = async (url, init) => {
    seen.push({ url: String(url), init, held: gate.claudeStatus().inflight_usd });
    if (answer instanceof Error) throw answer;
    if (typeof answer === 'function') return answer();
    return new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  const response = await route(ask(payload, headers), env, { gate, fetcher, now: () => NOW });
  return { response, seen, gate, meter: gate.claudeStatus(), bytes: new TextEncoder().encode(JSON.stringify(payload)).length };
}

test('the deployed price table is exactly Opus 5.5, Sonnet 5 and Sonnet 5.5 at the list prices, and the funded total is $100', () => {
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const variable = name => JSON.parse(new RegExp(`"${name}":\\s*("(?:[^"\\\\]|\\\\.)*")`).exec(config)[1]);
  const table = priceTable({ CLAUDE_MODELS: variable('CLAUDE_MODELS') });
  // Sonnet 5.5 (Sept 29, 2026): platform.claude.com/docs/en/about-claude/pricing lists it at Sonnet 5's prices. Every
  // row carries the US-only inference multiplier (1.1x on every rate for Claude 4.6 and later, "Data residency pricing").
  const us = { geo: { us: 1.1 } };
  assert.deepEqual(table, { 'claude-opus-5-5': { ...OPUS, ...us }, 'claude-sonnet-5': { ...SONNET, ...us }, 'claude-sonnet-5-5': { ...SONNET, ...us } });
  const deployed = settings({ CLAUDE_MODELS: variable('CLAUDE_MODELS') });
  assert.deepEqual(admit(body({ model: 'claude-sonnet-5-5' }), deployed),
    { model: 'claude-sonnet-5-5', price: { ...SONNET, ...us }, maxTokens: 16000, stream: false });
  // 2,000 x $2 + 10,000 x $2.50 + 30,000 x $0.20 + 6,000 x $10, per million: 0.004 + 0.025 + 0.006 + 0.06 = $0.095;
  // at 1.1x when Anthropic reports the call ran in the US ($0.1045, and a micro-dollar up: the meter rounds a cost up).
  assert.equal(actualCost(table['claude-sonnet-5-5'], USAGE), 95000n);
  const inUs = actualCost(table['claude-sonnet-5-5'], { ...USAGE, inference_geo: 'us' });
  assert.ok(inUs >= 104500n && inUs <= 104501n, String(inUs));
  const worst = worstCase(table['claude-sonnet-5-5'], 10000, 16000), plain = BigInt(Math.ceil((10000 + 4096) * 2.5 + 16000 * 10));
  assert.ok(worst >= plain * 11n / 10n && worst <= plain * 11n / 10n + 1n, `the worst case assumes the dearest geography: ${worst}`);
  assert.equal(variable('CLAUDE_USD'), '350');
  assert.equal(capMicro({ CLAUDE_USD: variable('CLAUDE_USD') }), 350000000n);
  assert.equal(capMicro({}), 0n, 'unset is no budget');
});

test('a price row that does not read is no price: its model is refused', () => {
  for (const change of [{ input: 'four' }, { output: 0 }, { cache_write: 3 }, { cache_read: 5 }, { cache_read: -1 }, { input: Infinity }]) {
    assert.deepEqual(priceTable({ CLAUDE_MODELS: JSON.stringify({ 'claude-opus-5-5': { ...OPUS, ...change } }) }), {}, JSON.stringify(change));
  }
  assert.deepEqual(priceTable({ CLAUDE_MODELS: JSON.stringify({ 'gpt-6-astra': OPUS }) }), {}, 'only Claude model ids');
  assert.deepEqual(priceTable({ CLAUDE_MODELS: 'opus=4' }), {});
  assert.deepEqual(priceTable({ CLAUDE_MODELS: '[1]' }), {});
});

test('settlement: uncached input, cache writes, cache reads and output each at its own rate', () => {
  // 2,000 x $4 + 10,000 x $5 + 30,000 x $0.20 + 6,000 x $20, per million: 0.008 + 0.05 + 0.006 + 0.12 = $0.184.
  assert.equal(actualCost(OPUS, USAGE), 184000n);
  // A cache read is a twentieth of the input rate on Opus 5.5: all-cached input costs 5% of all-uncached.
  assert.equal(actualCost(OPUS, { input_tokens: 0, cache_read_input_tokens: 1000000, output_tokens: 0 }), 200000n);
  assert.equal(actualCost(OPUS, { input_tokens: 1000000, output_tokens: 0 }), 4000000n);
  // Missing cache counts are zero; a one-hour write (never asked for) is priced at its list rate, twice the input rate.
  assert.equal(actualCost(SONNET, { input_tokens: 1000, output_tokens: 1000 }), 12000n);
  assert.equal(actualCost(OPUS, { input_tokens: 0, output_tokens: 0, cache_creation_input_tokens: 1000,
    cache_creation: { ephemeral_5m_input_tokens: 600, ephemeral_1h_input_tokens: 400 } }), 6200n);
  for (const usage of [null, 'x', [], {}, { input_tokens: 5 }, { output_tokens: 5 }, { input_tokens: -1, output_tokens: 1 },
    { input_tokens: 1.5, output_tokens: 1 }, { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 'many' }]) {
    assert.equal(actualCost(OPUS, usage), null, JSON.stringify(usage));
  }
  // The worst case: every input byte a token written to the cache, plus framing, and every output token used.
  assert.equal(worstCase(OPUS, 10000, 16000), BigInt(Math.ceil(((10000 + 4096) * 5 + 16000 * 20)))); // micro-dollars
  assert.ok(worstCase(OPUS, 0, 1) >= actualCost(OPUS, { input_tokens: 4096, output_tokens: 1 }));
});

test('admission: inline text, adaptive thinking, an effort and a JSON-schema format; everything that bills beyond the body is refused', () => {
  const env = settings();
  assert.deepEqual(admit(body(), env), { model: 'claude-opus-5-5', price: OPUS, maxTokens: 16000, stream: false });
  assert.equal(admit(body({ thinking: undefined, output_config: undefined }), env).model, 'claude-opus-5-5');
  assert.equal(admit(body({ system: 'plain', output_config: { effort: 'max', format: { type: 'json_schema', schema: { type: 'object' } } } }), env).maxTokens, 16000);
  assert.equal(admit(body({ messages: [{ role: 'user', content: [{ type: 'text', text: 'a', cache_control: { type: 'ephemeral', ttl: '5m' } }] }] }), env).model,
    'claude-opus-5-5');
  assert.equal(admit(body({ model: 'claude-opus-5' }), env).status, 403, 'unpriced');
  assert.equal(admit(body({ model: 'gpt-6-astra' }), env).status, 403);
  const mark = { type: 'ephemeral' };
  for (const change of [
    { temperature: 0.2 }, { top_p: 0.9 }, { tools: [{ name: 'x', input_schema: {} }] }, { tool_choice: { type: 'any' } }, { speed: 'fast' },
    { inference_geo: 'us' }, { service_tier: 'auto' }, { stream: 'true' }, { metadata: { user_id: 'x' } }, { mcp_servers: [] },
    { thinking: { type: 'disabled' } }, { thinking: { type: 'enabled', budget_tokens: 4000 } }, { thinking: { type: 'adaptive', display: 'raw' } },
    { output_config: { effort: 'extreme' } }, { output_config: { task_budget: { type: 'tokens', total: 20000 } } },
    { output_config: { format: { type: 'json_object' } } }, { max_tokens: MAX_TOKENS + 1 }, { max_tokens: 0 }, { max_tokens: '16000' },
    { messages: [] }, { messages: [{ role: 'user', content: 'q' }, { role: 'assistant', content: '{' }] },
    { messages: [{ role: 'system', content: 'x' }] }, { messages: [{ role: 'user', content: [{ type: 'image', source: {} }] }] },
    { messages: [{ role: 'user', content: [{ type: 'text', text: 'a', cache_control: { type: 'ephemeral', ttl: '1h' } }] }] },
    { messages: [{ role: 'user', content: [1, 2, 3, 4, 5].map(i => ({ type: 'text', text: String(i), cache_control: mark })) }] },
    { system: [{ type: 'text', text: 'a', citations: [] }] }, { system: 7 },
  ]) {
    assert.equal(admit(body(change), env).status, 400, JSON.stringify(change));
  }
});

test('routing: the House token is required, the key is added on the way out and never comes back, and the answer passes through', async () => {
  const unauthorized = await route(new Request('https://gw/v1/claude/messages', { method: 'POST', body: '{}' }), settings(),
    { gate: createGate({ store: memoryStore(), env: settings() }), fetcher: async () => { throw new Error('no call'); } });
  assert.equal(unauthorized.status, 401);
  const wrong = await route(ask(null, {}, '/v1/claude/messages', 'GET'), settings(), { gate: createGate({ store: memoryStore(), env: settings() }) });
  assert.equal(wrong.status, 405);

  const { response, seen, meter } = await call(body(), message(), { headers: { 'X-LTCM-Agent': 'swarm-architect', 'X-LTCM-Role': 'architect' } });
  assert.equal(response.status, 200);
  assert.equal(seen.length, 1);
  assert.equal(seen[0].url, 'https://api.anthropic.com/v1/messages');
  assert.equal(seen[0].init.headers['x-api-key'], KEY);
  assert.equal(seen[0].init.headers['anthropic-version'], '2023-06-01');
  assert.equal(seen[0].init.headers.Authorization, undefined, 'the House token is not forwarded');
  assert.deepEqual(JSON.parse(seen[0].init.body), body(), 'the body is forwarded as sent');
  const text = await response.text();
  assert.deepEqual(JSON.parse(text), message());
  assert.ok(!text.includes(KEY) && ![...response.headers.values()].some(v => v.includes(KEY)));
  assert.equal(response.headers.get('X-LTCM-Cost-USD'), '0.184000');
  assert.deepEqual([meter.spent_usd, meter.settled_usd, meter.inflight_usd, meter.calls], ['0.184000', '0.184000', '0.000000', 1]);
  assert.deepEqual(meter.by_role, { architect: '0.184000' });
  assert.deepEqual(meter.by_agent, { 'swarm-architect': '0.184000' });
  assert.deepEqual(meter.stops, { end_turn: 1 });

  // No key: a refusal that names its cap, and nothing is sent or held.
  const unset = await call(body(), message(), { env: settings({ CLAUDE_API_KEY: '' }) });
  assert.equal(unset.response.status, 503);
  assert.equal((await unset.response.json()).cap, 'setup');
  assert.equal(unset.seen.length, 0);
  // A body the gateway will not price: refused before any hold.
  const refused = await call(body({ speed: 'fast' }), message());
  assert.equal(refused.response.status, 400);
  assert.deepEqual([refused.seen.length, refused.meter.calls, refused.meter.spent_usd], [0, 0, '0.000000']);
});

test('the hold is the worst case while Anthropic works, and the funded total refuses a call that does not fit', async () => {
  const { seen, bytes } = await call(body(), message());
  assert.equal(seen[0].held, formatUsdMicro(worstCase(OPUS, bytes, 16000)));

  // $0.30 funded: a 16,000-token call's worst case ($0.32 of output alone, plus its input) does not fit.
  const tight = await call(body(), message(), { env: settings({ CLAUDE_USD: '0.30' }) });
  assert.equal(tight.response.status, 402);
  const refusal = await tight.response.json();
  assert.equal(refusal.cap, 'claude_funded');
  assert.match(refusal.error, /left of the \$0\.30 funded/);
  assert.equal(tight.seen.length, 0);
  // A smaller call fits.
  const small = await call(body({ max_tokens: 2000 }), message(), { env: settings({ CLAUDE_USD: '0.30' }) });
  assert.equal(small.response.status, 200);
  // No budget configured at all: every call is refused.
  assert.equal((await call(body(), message(), { env: settings({ CLAUDE_USD: undefined }) })).response.status, 403);
});

test('the funded total is not a month: what September spent still counts in October', async () => {
  const env = settings({ CLAUDE_USD: '1' });
  let at = Date.parse('2026-09-30T23:59:00Z');
  const gate = createGate({ store: memoryStore(), env, now: () => at });
  const fetcher = async () => new Response(JSON.stringify(message({ usage: { input_tokens: 0, output_tokens: 48000 } })), { status: 200 });
  assert.equal((await route(ask(body({ max_tokens: 1000 })), env, { gate, fetcher, now: () => at })).status, 200);
  assert.equal(gate.claudeStatus().spent_usd, '0.960000');
  at = Date.parse('2026-10-01T00:01:00Z');
  const next = await route(ask(body({ max_tokens: 1000 })), env, { gate, fetcher, now: () => at });
  assert.equal(next.status, 402, 'the October call does not find a fresh dollar');
  assert.equal(gate.claudeStatus().remaining_usd, '0.040000');
});

test('refusals and truncations are billed at their usage; a 4xx, a 5xx without usage and a lost answer settle at zero', async () => {
  const refusal = await call(body(), message({ stop_reason: 'refusal', content: [], usage: { input_tokens: 5000, output_tokens: 20 } }));
  assert.equal(refusal.response.status, 200, 'a refusal is an answer: the House reads its stop reason');
  assert.equal(refusal.response.headers.get('X-LTCM-Cost-USD'), '0.020400');
  assert.deepEqual([refusal.meter.spent_usd, refusal.meter.inflight_usd, refusal.meter.stops], ['0.020400', '0.000000', { refusal: 1 }]);

  const truncated = await call(body(), message({ stop_reason: 'max_tokens', usage: { input_tokens: 100, output_tokens: 16000 } }));
  assert.equal(truncated.meter.spent_usd, '0.320400');

  const error = (status, payload) => () => new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
  for (const [status, payload] of [[400, { type: 'error', error: { type: 'invalid_request_error', message: 'bad' } }],
    [429, { type: 'error', error: { type: 'rate_limit_error' } }], [500, { type: 'error', error: { type: 'api_error' } }],
    [529, { type: 'error', error: { type: 'overloaded_error' } }]]) {
    const out = await call(body(), error(status, payload));
    assert.equal(out.response.status, status);
    assert.equal(out.response.headers.get('X-LTCM-Cost-USD'), '0.000000', String(status));
    assert.deepEqual([out.meter.spent_usd, out.meter.inflight_usd, out.meter.calls], ['0.000000', '0.000000', 1], String(status));
    assert.deepEqual(out.meter.stops, { [`http_${status}`]: 1 });
  }
  // A 5xx that reports usage is billed for it.
  const partial = await call(body(), error(500, { type: 'error', usage: { input_tokens: 1000000, output_tokens: 0 } }));
  assert.equal(partial.meter.spent_usd, '4.000000');

  const lost = await call(body(), new TypeError('network connection lost'));
  assert.equal(lost.response.status, 502);
  assert.equal(lost.response.headers.get('X-LTCM-Cost-USD'), '0.000000');
  assert.deepEqual([lost.meter.spent_usd, lost.meter.inflight_usd, lost.meter.stops], ['0.000000', '0.000000', { no_answer: 1 }]);
  // Anthropic's headers came and then the body was cut off: the call ran, so its worst case stays spent (item 1 of the review).
  const cut = await call(body(), () => ({ ok: true, status: 200, headers: new Headers(), text: async () => { throw new Error('cut off'); } }));
  assert.equal(cut.response.status, 502);
  assert.equal(cut.response.headers.get('X-LTCM-Cost-Known'), 'false');
  assert.equal(cut.response.headers.get('X-LTCM-Cost-USD'), formatUsdMicro(worstCase(OPUS, cut.bytes, 16000)));
  assert.deepEqual([cut.meter.spent_usd, cut.meter.inflight_usd, cut.meter.stops],
    [formatUsdMicro(worstCase(OPUS, cut.bytes, 16000)), '0.000000', { body_cut: 1 }]);

  // A 2xx whose usage cannot be read keeps its whole hold: unknown is not free.
  const unknown = await call(body(), message({ usage: undefined }));
  assert.equal(unknown.response.status, 200);
  assert.equal(unknown.meter.spent_usd, formatUsdMicro(worstCase(OPUS, unknown.bytes, 16000)));
  assert.equal(unknown.meter.inflight_usd, '0.000000');
  assert.equal(unknown.response.headers.get('X-LTCM-Cost-Known'), 'false');
});

test('the kill switch stops Claude calls before any hold, and releasing it lets them through', async () => {
  const env = settings();
  const gate = createGate({ store: memoryStore(), env, now: () => NOW });
  gate.setKill(true);
  const killed = await call(body(), message(), { env, gate });
  assert.equal(killed.response.status, 423);
  assert.equal((await killed.response.json()).cap, 'kill_switch');
  assert.deepEqual([killed.seen.length, killed.meter.calls, killed.meter.spent_usd], [0, 0, '0.000000']);
  gate.setKill(false);
  assert.equal((await call(body(), message(), { env, gate })).response.status, 200);
});

test('/v1/health reports Claude\'s funded meter, and /v1/claude/models what the key reaches', async () => {
  const env = settings();
  const gate = createGate({ store: memoryStore(), env, now: () => NOW });
  await call(body(), message(), { env, gate, headers: { 'X-LTCM-Role': 'diagnostician' } });
  const health = await (await route(ask(null, {}, '/v1/health', 'GET'), env, { gate, now: () => NOW })).json();
  assert.deepEqual(health.claude, {
    funded: true, cap_usd: '100.00', spent_usd: '0.184000', settled_usd: '0.184000', inflight_usd: '0.000000', remaining_usd: '99.816000',
    calls: 1, holds: 0, stale_holds: 0, swept: 0, swept_usd: '0.000000', overruns: 0, overrun_usd: '0.000000',
    models: ['claude-opus-5-5', 'claude-sonnet-5'], configured: true,
    by_role: { diagnostician: '0.184000' }, by_agent: { unattributed: '0.184000' }, stops: { end_turn: 1 }, geos: {},
  });
  assert.ok(!JSON.stringify(health).includes(KEY));

  const seen = [];
  const fetcher = async (url, init) => {
    seen.push({ url: String(url), init });
    return new Response(JSON.stringify({ data: [{ id: 'claude-sonnet-5' }, { id: 'claude-opus-5-5' }, { id: 7 }] }), { status: 200 });
  };
  const models = await (await route(ask(null, {}, '/v1/claude/models', 'GET'), env, { gate, fetcher })).json();
  assert.deepEqual(models, { models: ['claude-opus-5-5', 'claude-sonnet-5'], priced: ['claude-opus-5-5', 'claude-sonnet-5'] });
  assert.equal(seen[0].url, 'https://api.anthropic.com/v1/models?limit=100');
  assert.equal(seen[0].init.headers['x-api-key'], KEY);
  const down = await route(ask(null, {}, '/v1/claude/models', 'GET'), env, { gate, fetcher: async () => new Response('{}', { status: 401 }) });
  assert.equal(down.status, 502);
});

test('a hold no settlement replaced is swept to zero after half an hour, and a late settlement still books its cost', () => {
  const env = settings();
  let at = NOW;
  const gate = createGate({ store: memoryStore(), env, now: () => at });
  const lost = gate.claudeReserve({ micro: '400000', request: 'swarm:architect:1', at });
  assert.equal(lost.ok, true);
  assert.deepEqual(gate.claudeRequest('swarm:architect:1'), { request: 'swarm:architect:1', state: 'held', cost_usd: null });
  at += 29 * 60 * 1000;
  assert.equal(gate.claudeSweep({ at }), 0, 'not yet stale');
  assert.equal(gate.claudeStatus(at).inflight_usd, '0.400000');
  at += 2 * 60 * 1000;
  assert.equal(gate.claudeStatus(at).stale_holds, 1);
  // The next call sweeps first: the lost hold no longer shrinks the funded total.
  const next = gate.claudeReserve({ micro: '100000', request: 'swarm:audit:2', at });
  assert.equal(next.ok, true);
  let meter = gate.claudeStatus(at);
  assert.deepEqual([meter.spent_usd, meter.inflight_usd, meter.holds, meter.swept, meter.swept_usd], ['0.100000', '0.100000', 1, 1, '0.400000']);
  assert.deepEqual(gate.claudeRequest('swarm:architect:1'), { request: 'swarm:architect:1', state: 'released', cost_usd: '0.000000' });
  // The lost call's settlement arrives after all: its cost is booked, and nothing is released twice.
  gate.claudeSettle({ id: lost.id, reserved: '400000', actual: '150000', at });
  gate.claudeSettle({ id: next.id, reserved: '100000', actual: '20000', at });
  meter = gate.claudeStatus(at);
  assert.deepEqual([meter.spent_usd, meter.inflight_usd, meter.holds], ['0.170000', '0.000000', 0]);
  assert.deepEqual(gate.claudeRequest('swarm:audit:2'), { request: 'swarm:audit:2', state: 'settled', cost_usd: '0.020000' });
  assert.deepEqual(gate.claudeRequest('never-sent'), { request: 'never-sent', state: 'absent' });
  assert.deepEqual(gate.claudeRequest('bad id!'), { request: null, state: 'absent' });
});

test('/v1/claude/request/<id> tells the House what became of its call: settled, unknown or absent', async () => {
  const env = settings();
  const gate = createGate({ store: memoryStore(), env, now: () => NOW });
  await call(body(), message(), { env, gate, headers: { 'X-LTCM-Request': 'swarm:condor:diagnose:2:1790:ab12' } });
  await call(body(), message({ usage: undefined }), { env, gate, headers: { 'X-LTCM-Request': 'swarm:condor:audit:3:0:cd34' } });
  const read = async id => (await route(ask(null, {}, `/v1/claude/request/${id}`, 'GET'), env, { gate, now: () => NOW })).json();
  assert.deepEqual(await read('swarm:condor:diagnose:2:1790:ab12'), { request: 'swarm:condor:diagnose:2:1790:ab12', state: 'settled', cost_usd: '0.184000' });
  const unknown = await read('swarm:condor:audit:3:0:cd34');
  assert.equal(unknown.state, 'unknown');
  assert.ok(Number(unknown.cost_usd) > 0.32, 'an unknown bill is booked at its worst case');
  assert.deepEqual(await read('swarm:elsewhere'), { request: 'swarm:elsewhere', state: 'absent' });
  assert.equal((await route(ask(null, {}, '/v1/claude/request/x', 'POST'), env, { gate })).status, 405);
  assert.equal((await route(new Request('https://gw/v1/claude/request/x'), env, { gate })).status, 401);
});

test('the inference geography is recorded, and priced only by a multiplier CLAUDE_MODELS names', async () => {
  const usage = { ...USAGE, inference_geo: 'us' };
  assert.equal(actualCost(OPUS, usage), 184000n, 'no multiplier configured: the rates stand');
  const geo = priceTable({ CLAUDE_MODELS: JSON.stringify({ 'claude-opus-5-5': { ...OPUS, geo: { us: 1.1, cheap: 0.5, 'Bad Geo': 2 } } }) })['claude-opus-5-5'];
  assert.deepEqual(geo.geo, { us: 1.1 });
  const priced = actualCost(geo, usage);
  assert.ok(priced >= 202400n && priced <= 202401n, `1.1 x $0.184, rounded up at most a micro-dollar: ${priced}`);
  assert.equal(actualCost(geo, { ...usage, inference_geo: 'global' }), 184000n);
  assert.ok(worstCase(geo, 1000, 1000) > worstCase(OPUS, 1000, 1000), 'the worst case assumes the dearest geography');
  const out = await call(body(), message({ usage }));
  assert.deepEqual(out.meter.geos, { us: 1 });
  assert.equal(out.meter.spent_usd, '0.184000');
});
