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
