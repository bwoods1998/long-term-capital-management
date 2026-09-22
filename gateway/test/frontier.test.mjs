import test from 'node:test';
import assert from 'node:assert/strict';
import { priceTable, actualCost, worstCase, admit } from '../lib/frontier.mjs';

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
