import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { priceTable, actualCost, worstCase, admit, roleCeilings, outputCeiling, MAX_OUTPUT_TOKENS, ROLE_MAX_OUTPUT_LIMIT } from '../lib/frontier.mjs';
import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { formatUsdMicro } from '../lib/money.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const env = { FRONTIER_MODELS: JSON.stringify({ luna: {
  input: .25, cached: .02, output: 1.2, long_input: .5, long_cached: .04, long_output: 1.8,
} }) };
const price = priceTable(env).luna;
const body = { model: 'luna', input: [{ role: 'user', content: 'hello' }], max_output_tokens: 6000 };

test('reservations cover byte-level tokenization, framing and long-context premiums', () => {
  assert.equal(worstCase(price, 300000, 6000), 162848n);
  assert.equal(actualCost(price, { input_tokens: 300000, output_tokens: 6000,
    input_tokens_details: { cached_tokens: 100000 } }), 114800n);
  assert.equal(actualCost(price, { input_tokens: 1000, output_tokens: 1000 }), 1450n);
  assert.equal(actualCost(price, null), null);
});

test('text-only standard calls cannot conceal paid inputs, tools or priority processing', () => {
  assert.equal(admit(body, env).model, 'luna');
  for (const change of [{ tools: [{ type: 'web_search' }] }, { previous_response_id: 'resp_old' },
    { conversation: 'conv_old' }, { service_tier: 'priority' }, { service_tier: 'fast' },
    { input: [{ role: 'user', content: [{ type: 'input_image', image_url: 'https://example.test' }] }] },
    { input: [{ role: 'user', content: 'hello', attachments: ['file_old'] }] }]) {
    assert.equal(admit({ ...body, ...change }, env).status, 400, JSON.stringify(change));
  }
});

test('invalid and underpriced long-context tables fail closed', () => {
  for (const change of [{ input: 'Infinity' }, { output: 'NaN' }, { cached: 1 }, { long_input: .1 },
    { long_cached: 1 }, { long_output: 1 }]) {
    assert.deepEqual(priceTable({ FRONTIER_MODELS: JSON.stringify({ bad: { ...price, ...change } }) }), {});
  }
});

test('prompt-cache hints pass through, bounded; anything else about the cache is refused', () => {
  const block = text => ({ type: 'input_text', text, prompt_cache_breakpoint: { mode: 'explicit' } });
  const cached = { ...body, prompt_cache_key: 'research:openai_luna:v2', prompt_cache_options: { mode: 'explicit', ttl: '30m' },
    input: [{ role: 'developer', content: [block('rules')] }, { role: 'user', content: [block('agent'), { type: 'input_text', text: 'now' }] },
      { role: 'assistant', content: '{"name":"finish"}' }, { role: 'user', content: 'result' }] };
  assert.equal(admit(cached, env).model, 'luna');
  assert.equal(admit({ ...body, prompt_cache_retention: '24h' }, env).model, 'luna');
  assert.equal(admit({ ...body, prompt_cache_options: { mode: 'implicit' } }, env).model, 'luna');
  for (const change of [{ prompt_cache_key: '' }, { prompt_cache_key: 'x'.repeat(65) }, { prompt_cache_key: 'has space' },
    { prompt_cache_key: 7 }, { prompt_cache_retention: 'forever' }, { prompt_cache_options: { mode: 'magic' } },
    { prompt_cache_options: { ttl: '24h' } }, { prompt_cache_options: { prewarm: true } }, { prompt_cache_options: { other: 1 } },
    { prompt_cache_options: 'explicit' },
    { input: [{ role: 'user', content: [block('a'), block('b'), block('c'), block('d'), block('e')] }] },
    { input: [{ role: 'user', content: [{ type: 'input_text', text: 'x', prompt_cache_breakpoint: { mode: 'implicit' } }] }] },
    { input: [{ role: 'user', content: [{ type: 'input_text', text: 'x', extra: 1 }] }] },
    { input: [{ role: 'assistant', content: [block('a')] }] },
    { input: [{ role: 'user', content: [] }] }]) {
    assert.equal(admit({ ...body, ...change }, env).status, 400, JSON.stringify(change));
  }
});

test('cache writes, reads and plain input are each settled at their own rate', () => {
  const table = priceTable({ FRONTIER_MODELS: JSON.stringify({ luna: {
    input: .25, uncached: .2, cached: .02, output: 1.2, long_input: .5, long_uncached: .4, long_cached: .04, long_output: 1.8,
  } }) }).luna;
  // 10,000 read at .02, 4,000 written at .25, 6,000 neither at .20, 1,000 out at 1.2.
  assert.equal(actualCost(table, { input_tokens: 20000, output_tokens: 1000,
    input_tokens_details: { cached_tokens: 10000, cache_write_tokens: 4000 } }), 3600n);
  // Without the write count every uncached token is priced as a write: the meter errs high.
  assert.equal(actualCost(table, { input_tokens: 20000, output_tokens: 1000, input_tokens_details: { cached_tokens: 10000 } }), 3900n);
  // A write count larger than what was not read cannot push the bill below the write rate.
  assert.equal(actualCost(table, { input_tokens: 20000, output_tokens: 1000,
    input_tokens_details: { cached_tokens: 10000, cache_write_tokens: 99999 } }), 3900n);
  // Tables without `uncached` price exactly as before.
  assert.equal(actualCost(price, { input_tokens: 20000, output_tokens: 1000,
    input_tokens_details: { cached_tokens: 10000, cache_write_tokens: 4000 } }), 3900n);
  for (const change of [{ uncached: .3 }, { uncached: .01 }, { long_uncached: .6 }]) {
    assert.deepEqual(priceTable({ FRONTIER_MODELS: JSON.stringify({ bad: { ...table, ...change } }) }), {}, JSON.stringify(change));
  }
});

// ------------------------------------------------ flex and role ceilings (Sept 26, 2026 (the options-swarm run, Wave 5))

//: GPT-6 Luna as wrangler.jsonc prices it, standard and flex (exactly half of each standard rate).
const LUNA = { input: 0.125, cached: 0.01, output: 0.5, long_input: 0.25, long_cached: 0.02, long_output: 0.75, uncached: 0.1, long_uncached: 0.2 };
const LUNA_FLEX = Object.fromEntries(Object.entries(LUNA).map(([key, value]) => [key, value / 2]));
const flexEnv = { FRONTIER_MODELS: JSON.stringify({ 'gpt-6-luna': { ...LUNA, flex: LUNA_FLEX }, plain: LUNA }) };

test('flex rates: a model\'s flex row is read and checked against its standard rates; a model without one cannot go flex', () => {
  const table = priceTable(flexEnv);
  assert.deepEqual(table['gpt-6-luna'].flex, LUNA_FLEX);
  assert.equal(table.plain.flex, undefined);
  // A flex row that leaves the long-context rates out takes the standard ones: the meter errs high.
  const short = priceTable({ FRONTIER_MODELS: JSON.stringify({ m: { ...LUNA, flex: { input: 0.0625, cached: 0.005, output: 0.25 } } }) }).m.flex;
  assert.deepEqual([short.long_input, short.long_cached, short.long_output, short.uncached, short.long_uncached], [0.25, 0.02, 0.75, 0.0625, 0.2]);
  // A flex rate above its standard rate, or one that does not read, is no flex price; the model's standard price stands.
  for (const flex of [{ ...LUNA_FLEX, output: 0.6 }, { ...LUNA_FLEX, cached: 0.2 }, { ...LUNA_FLEX, input: 'cheap' }, 'half', [LUNA_FLEX], { ...LUNA_FLEX, long_output: 1 }]) {
    const row = priceTable({ FRONTIER_MODELS: JSON.stringify({ m: { ...LUNA, flex } }) }).m;
    assert.equal(row.input, 0.125, JSON.stringify(flex));
    assert.equal(row.flex, undefined, JSON.stringify(flex));
  }
  const body = { model: 'gpt-6-luna', input: 'Audit this.', max_output_tokens: 1000 };
  assert.deepEqual(admit({ ...body, service_tier: 'flex' }, flexEnv).flex, LUNA_FLEX);
  assert.equal(admit({ ...body, service_tier: 'default' }, flexEnv).flex, null);
  assert.equal(admit(body, flexEnv).flex, null);
  assert.deepEqual(admit({ ...body, model: 'plain', service_tier: 'flex' }, flexEnv),
    { error: 'No flex price is configured for model "plain"; a flex call is refused.', status: 403 });
  for (const tier of ['priority', 'scale', 'auto', 'FLEX', '']) assert.equal(admit({ ...body, service_tier: tier }, flexEnv).status, 400, tier);
});

test('role ceilings: 16,000 by default; FRONTIER_ROLE_MAX_OUTPUT names a role\'s own, and nothing else changes', () => {
  const env = { ...flexEnv, FRONTIER_ROLE_MAX_OUTPUT: JSON.stringify({ postmortem: 64000 }) };
  const body = tokens => ({ model: 'gpt-6-luna', input: 'Write the week.', max_output_tokens: tokens });
  assert.equal(admit(body(16000), env).maxOutput, 16000);
  assert.deepEqual(admit(body(16001), env), { error: 'max_output_tokens is required, between 1 and 16000.', status: 400 });
  assert.equal(admit(body(64000), env, { role: 'postmortem' }).maxOutput, 64000);
  assert.equal(admit(body(64000), env, { role: 'postmortem' }).ceiling, 64000);
  assert.deepEqual(admit(body(64001), env, { role: 'postmortem' }), { error: 'max_output_tokens is required, between 1 and 64000.', status: 400 });
  for (const role of ['teacher', 'Postmortem', 'postmortem ', '', null, undefined, '../postmortem', 'x'.repeat(65)]) {
    assert.equal(admit(body(16001), env, { role }).status, 400, String(role));
    assert.equal(outputCeiling(env, role), MAX_OUTPUT_TOKENS, String(role));
  }
  // A table that does not read raises nothing; an entry that is not a whole number from 1 to the limit is not read.
  assert.deepEqual(roleCeilings({ FRONTIER_ROLE_MAX_OUTPUT: 'postmortem=64000' }), {});
  assert.deepEqual(roleCeilings({ FRONTIER_ROLE_MAX_OUTPUT: '[64000]' }), {});
  assert.deepEqual(roleCeilings({ FRONTIER_ROLE_MAX_OUTPUT: JSON.stringify({
    postmortem: ROLE_MAX_OUTPUT_LIMIT + 1, a: '64000', b: 1.5, c: 0, 'Bad Role': 20000, d: 20000 }) }), { d: 20000 });
  assert.equal(outputCeiling({}, 'postmortem'), MAX_OUTPUT_TOKENS);
});

const frontierSettings = extra => ({
  GATEWAY_TOKEN: TOKEN, OPENAI_SECRET_KEY: 'sk-test', FRONTIER_MONTH_USD: '10', ...flexEnv,
  FRONTIER_ROLE_MAX_OUTPUT: JSON.stringify({ postmortem: 64000 }), ...extra,
});
const NOW = Date.parse('2026-09-28T14:00:00Z');
const askFrontier = (body, headers = {}) => new Request('https://gw/v1/frontier/responses', {
  method: 'POST', body: JSON.stringify(body), headers: { Authorization: `Bearer ${TOKEN}`, ...headers },
});

/** One frontier call through the front door: the answer, what the gate held while the provider worked, and what it settled. */
async function frontierCall(body, answer, { headers = {}, settings = frontierSettings() } = {}) {
  const gate = createGate({ store: memoryStore(), env: settings, now: () => NOW });
  const seen = [];
  const fetcher = async (url, init) => {
    seen.push({ url: String(url), body: init.body, held: gate.status(NOW).frontier.inflight_usd });
    return typeof answer === 'function' ? answer() : new Response(JSON.stringify(answer), { status: 200 });
  };
  const response = await route(askFrontier(body, headers), settings, { gate, fetcher, now: () => NOW });
  return { response, seen, month: gate.status(NOW).frontier, bytes: new TextEncoder().encode(JSON.stringify(body)).length };
}

test('a flex call is reserved at the standard worst case and settled at flex rates only when the answer says flex; a 429 settles at zero', async () => {
  const body = { model: 'gpt-6-luna', input: 'Replay the week.', max_output_tokens: 8000, service_tier: 'flex' };
  const usage = { input_tokens: 20000, output_tokens: 4000, input_tokens_details: { cached_tokens: 10000, cache_write_tokens: 0 } };
  const standard = priceTable(flexEnv)['gpt-6-luna'];
  const flexCost = formatUsdMicro(actualCost(LUNA_FLEX, usage));
  const standardCost = formatUsdMicro(actualCost(standard, usage));
  assert.notEqual(flexCost, standardCost);

  const served = await frontierCall(body, { service_tier: 'flex', usage });
  assert.equal(served.response.status, 200);
  assert.equal(JSON.parse(served.seen[0].body).service_tier, 'flex', 'the tier reaches OpenAI as asked');
  assert.equal(served.seen[0].held, formatUsdMicro(worstCase(standard, served.bytes, 8000)), 'held at the STANDARD worst case');
  assert.equal(served.response.headers.get('X-LTCM-Cost-USD'), flexCost);
  assert.equal(served.response.headers.get('X-LTCM-Billed-Tier'), 'flex');
  assert.deepEqual([served.month.settled_usd, served.month.inflight_usd], [flexCost, '0.000000']);

  // Served on another tier, or silent about it: the standard rates.
  for (const answer of [{ service_tier: 'default', usage }, { usage }, { service_tier: 'priority', usage }]) {
    const other = await frontierCall(body, answer);
    assert.equal(other.response.headers.get('X-LTCM-Cost-USD'), standardCost, JSON.stringify(answer.service_tier));
    assert.equal(other.response.headers.get('X-LTCM-Billed-Tier'), 'default');
  }
  // A call that did not ask for flex is never settled at flex rates, whatever the answer says.
  const unasked = await frontierCall({ ...body, service_tier: undefined }, { service_tier: 'flex', usage });
  assert.equal(unasked.response.headers.get('X-LTCM-Cost-USD'), standardCost);

  // No flex capacity: OpenAI's 429 bills nothing, and the hold is released.
  const busy = await frontierCall(body, () => new Response(JSON.stringify({ error: { type: 'rate_limit_error', code: 'resource_unavailable' } }), { status: 429 }));
  assert.equal(busy.response.status, 429);
  assert.equal(busy.response.headers.get('X-LTCM-Cost-USD'), '0.000000');
  assert.deepEqual([busy.month.settled_usd, busy.month.inflight_usd, busy.month.calls], ['0.000000', '0.000000', 1]);

  // A model with no flex price is refused before anything is held or sent.
  const refused = await frontierCall({ ...body, model: 'plain' }, { usage });
  assert.equal(refused.response.status, 403);
  assert.equal(refused.seen.length, 0);
  assert.equal(refused.month.calls, 0);
});

test('X-LTCM-Role raises the ceiling for its role only, and the reservation is sized from what was admitted', async () => {
  const body = { model: 'gpt-6-luna', input: 'The weekly post-mortem.', max_output_tokens: 64000 };
  const usage = { input_tokens: 100, output_tokens: 50000 };
  const standard = priceTable(flexEnv)['gpt-6-luna'];
  const admitted = await frontierCall(body, { usage }, { headers: { 'X-LTCM-Role': 'postmortem' } });
  assert.equal(admitted.response.status, 200);
  assert.equal(admitted.seen[0].held, formatUsdMicro(worstCase(standard, admitted.bytes, 64000)));
  assert.equal(admitted.response.headers.get('X-LTCM-Cost-USD'), formatUsdMicro(actualCost(standard, usage)));
  for (const headers of [{}, { 'X-LTCM-Role': 'teacher' }, { 'X-LTCM-Role': 'POSTMORTEM' }]) {
    const refused = await frontierCall(body, { usage }, { headers });
    assert.equal(refused.response.status, 400, JSON.stringify(headers));
    assert.match((await refused.response.json()).error, /between 1 and 16000/);
    assert.equal(refused.seen.length, 0);
  }
  // Without the var, the post-mortem is held to 16,000 like every call.
  const unset = await frontierCall(body, { usage }, { headers: { 'X-LTCM-Role': 'postmortem' }, settings: frontierSettings({ FRONTIER_ROLE_MAX_OUTPUT: undefined }) });
  assert.equal(unset.response.status, 400);
});

test('the deployed flex rates are exactly half of each standard rate for Astra, Sol and Luna, and the post-mortem\'s ceiling is 64,000', () => {
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const variable = name => JSON.parse(JSON.parse(new RegExp(`"${name}":\\s*("(?:[^"\\\\]|\\\\.)*")`).exec(config)[1]));
  const models = variable('FRONTIER_MODELS');
  const table = priceTable({ FRONTIER_MODELS: JSON.stringify(models) });
  for (const model of ['gpt-6-astra', 'gpt-6-sol', 'gpt-6-luna']) {
    const row = models[model];
    for (const field of ['input', 'cached', 'output', 'long_input', 'long_cached', 'long_output', 'uncached', 'long_uncached']) {
      assert.equal(row.flex[field] * 2, row[field], `${model} ${field}`);
    }
    assert.deepEqual(table[model].flex, row.flex, `${model}: the deployed flex row reads`);
  }
  for (const model of ['gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna']) assert.equal(table[model].flex, undefined, model);
  assert.deepEqual(variable('FRONTIER_ROLE_MAX_OUTPUT'), { postmortem: 64000 });
});
