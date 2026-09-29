// The House's own tools through the Claude route (Sept 29, 2026: the swarm's top researchers run their tool loop on
// Claude Sonnet 5.5). What is admitted (custom tools, auto or none, the loop's tool_use / tool_result / thinking turns), what
// is still refused (anything that runs or bills beyond the body), that the reservation counts the tools and every turn,
// and that a streamed tool_use answer settles at its usage. No network: the fetcher stands in for Anthropic.
import test from 'node:test';
import assert from 'node:assert/strict';
import { admit, sseParser, worstCase, MAX_TOOLS, MAX_BLOCKS } from '../lib/claude.mjs';
import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { formatUsdMicro } from '../lib/money.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const KEY = 'anthropic-test-key-never-leaves-the-worker';
const SONNET = { input: 2, cache_write: 2.5, cache_read: 0.2, output: 10 };
const MODELS = JSON.stringify({ 'claude-sonnet-5-5': SONNET, 'claude-opus-5-5': { input: 4, cache_write: 5, cache_read: 0.2, output: 20 } });
const settings = extra => ({ GATEWAY_TOKEN: TOKEN, CLAUDE_API_KEY: KEY, CLAUDE_USD: '100', CLAUDE_MODELS: MODELS, ...extra });
const NOW = Date.parse('2026-09-29T05:00:00Z');
const mark = { type: 'ephemeral' };

const schema = properties => ({ type: 'object', properties });
/** The researcher's tools as the House declares them: eager input streaming, a marker on the last. */
const TOOLS = ['gym_run', 'gym_sweep', 'read_run', 'notebook', 'graveyard', 'submit', 'retire'].map((name, i, all) => ({
  name, description: `The ${name} tool.`, input_schema: schema({ note: { type: 'string' } }), eager_input_streaming: true,
  ...(i === all.length - 1 ? { cache_control: mark } : {}),
}));
const SIGNATURE = 'EqQBCgIYAhIM1gbcDa9GJwZA2b3hGgxBdjrkzLoky3dl1pkiMOYds';
/** A researcher's cycle on Claude: brief and status, a call, its result, parallel calls (one from `caller: direct`). */
const LOOP = [
  { role: 'user', content: [{ type: 'text', text: 'YOUR FAMILY: condor' }, { type: 'text', text: 'Cycle 5. Now: revise.' }] },
  { role: 'assistant', content: [
    { type: 'thinking', thinking: '', signature: SIGNATURE },
    { type: 'text', text: 'Widening the wings.', citations: null },
    { type: 'tool_use', id: 'toolu_01A', name: 'gym_run', input: { code: 'PARAMS = {}', why: 'wider' } },
  ] },
  { role: 'user', content: [
    { type: 'tool_result', tool_use_id: 'toolu_01A', content: '{"status": "ok", "run_id": "run-1"}' },
    { type: 'text', text: 'Tools offered now: every tool.' },
  ] },
  { role: 'assistant', content: [
    { type: 'thinking', thinking: 'A summary of the reasoning.', signature: SIGNATURE },
    { type: 'redacted_thinking', data: 'ZW5jcnlwdGVk' },
    { type: 'tool_use', id: 'toolu_01B', name: 'notebook', input: { action: 'append', text: 'Wider wings.' } },
    { type: 'tool_use', id: 'toolu_01C', name: 'submit', input: { run_id: 'run-1' }, caller: { type: 'direct' } },
  ] },
  { role: 'user', content: [
    { type: 'tool_result', tool_use_id: 'toolu_01B', content: [{ type: 'text', text: '{"ok": true}' }] },
    { type: 'tool_result', tool_use_id: 'toolu_01C', content: '{"error": "INVALID_JSON"}', is_error: true },
    { type: 'text', text: 'Tools offered now: every tool.', cache_control: mark },
  ] },
];
const body = (extra = {}) => ({
  model: 'claude-sonnet-5-5', max_tokens: 16000, stream: true, thinking: { type: 'adaptive', display: 'summarized' },
  output_config: { effort: 'medium' }, system: [{ type: 'text', text: 'You are a researcher.', cache_control: mark }],
  tools: TOOLS, tool_choice: { type: 'auto' }, messages: LOOP, ...extra,
});
const turn = (role, block) => ({ role, content: [block] });
const withTurn = (role, block) => body({ messages: [...LOOP.slice(0, -1), turn(role, block), LOOP.at(-1)] });
const replaceTool = change => body({ tools: [{ ...TOOLS[0], ...change }, ...TOOLS.slice(1)] });

test('admission: the researcher\'s real tool loop is admitted, streamed or not, with auto or none', () => {
  const env = settings();
  assert.deepEqual(admit(body(), env), { model: 'claude-sonnet-5-5', price: SONNET, maxTokens: 16000, stream: true });
  assert.equal(admit(body({ tool_choice: { type: 'none' } }), env).model, 'claude-sonnet-5-5');
  assert.equal(admit(body({ tool_choice: { type: 'auto', disable_parallel_tool_use: true } }), env).model, 'claude-sonnet-5-5');
  assert.equal(admit(body({ tool_choice: undefined }), env).model, 'claude-sonnet-5-5', 'auto is the default');
  assert.equal(admit(body({ stream: undefined, thinking: { type: 'adaptive' } }), env).stream, false);
  // The first turn of a cycle: the brief and the status, no call yet, one marker on its last block.
  assert.equal(admit(body({ messages: [{ role: 'user', content: [{ type: 'text', text: 'brief' }, { type: 'text', text: 'status', cache_control: mark }] }] }), env).model,
    'claude-sonnet-5-5');
  // Up to MAX_TOOLS tools and MAX_BLOCKS blocks a turn.
  const many = Array.from({ length: MAX_TOOLS }, (_, i) => ({ name: `tool_${i}`, input_schema: { type: 'object' } }));
  assert.equal(admit(body({ tools: many }), env).model, 'claude-sonnet-5-5');
  const blocks = Array.from({ length: MAX_BLOCKS }, (_, i) => ({ type: 'text', text: String(i) }));
  assert.equal(admit(body({ messages: [{ role: 'user', content: blocks }] }), env).model, 'claude-sonnet-5-5');
});

test('admission: everything that runs or bills beyond the body, or that Sonnet 5.5 refuses, is still refused', () => {
  const env = settings();
  const refusals = {
    'a web search tool': body({ tools: [...TOOLS, { type: 'web_search_20260209', name: 'web_search' }] }),
    'a bash tool': body({ tools: [...TOOLS, { type: 'bash_20250124', name: 'bash' }] }),
    'a custom tool with a type': replaceTool({ type: 'custom' }),
    'strict': replaceTool({ strict: true }),
    'defer_loading': replaceTool({ defer_loading: true }),
    'allowed_callers': replaceTool({ allowed_callers: ['code_execution_20260120'] }),
    'input_examples': replaceTool({ input_examples: [{}] }),
    'a bad tool name': replaceTool({ name: 'gym run' }),
    'a duplicate tool name': body({ tools: [TOOLS[0], TOOLS[0]] }),
    'an input_schema that is not an object': replaceTool({ input_schema: { type: 'string' } }),
    'no input_schema': replaceTool({ input_schema: undefined }),
    'a one-hour marker on a tool': replaceTool({ cache_control: { type: 'ephemeral', ttl: '1h' } }),
    'eager_input_streaming that is not a boolean': replaceTool({ eager_input_streaming: 'yes' }),
    'no tools at all': body({ tools: [] }),
    'too many tools': body({ tools: Array.from({ length: MAX_TOOLS + 1 }, (_, i) => ({ name: `t${i}`, input_schema: { type: 'object' } })) }),
    'tool_choice any': body({ tool_choice: { type: 'any' } }),
    'tool_choice tool': body({ tool_choice: { type: 'tool', name: 'gym_run' } }),
    'tool_choice without tools': body({ tools: undefined, messages: [LOOP[0]] }),
    'tool_choice as a string': body({ tool_choice: 'auto' }),
    'a thinking block with an empty signature': withTurn('assistant', { type: 'thinking', thinking: '', signature: '' }),
    'a thinking block without a signature': withTurn('assistant', { type: 'thinking', thinking: 'x' }),
    'a thinking block with a marker': withTurn('assistant', { type: 'thinking', thinking: '', signature: SIGNATURE, cache_control: mark }),
    'an empty redacted thinking block': withTurn('assistant', { type: 'redacted_thinking', data: '' }),
    'a thinking block in a user turn': withTurn('user', { type: 'thinking', thinking: '', signature: SIGNATURE }),
    'a call from code execution': withTurn('assistant', { type: 'tool_use', id: 'toolu_9', name: 'gym_run', input: {},
      caller: { type: 'code_execution_20260120', tool_id: 'srvtoolu_1' } }),
    'a call whose input is not an object': withTurn('assistant', { type: 'tool_use', id: 'toolu_9', name: 'gym_run', input: '{}' }),
    'a call with a bad id': withTurn('assistant', { type: 'tool_use', id: 'toolu 9', name: 'gym_run', input: {} }),
    'a tool_use in a user turn': withTurn('user', { type: 'tool_use', id: 'toolu_9', name: 'gym_run', input: {} }),
    'a tool_result in an assistant turn': withTurn('assistant', { type: 'tool_result', tool_use_id: 'toolu_9', content: 'x' }),
    'a tool_result holding an image': withTurn('user', { type: 'tool_result', tool_use_id: 'toolu_9',
      content: [{ type: 'image', source: { type: 'url', url: 'https://x/y.png' } }] }),
    'a tool_result with is_error not a boolean': withTurn('user', { type: 'tool_result', tool_use_id: 'toolu_9', content: 'x', is_error: 'yes' }),
    'an image block': withTurn('user', { type: 'image', source: { type: 'base64', media_type: 'image/png', data: 'AAAA' } }),
    'a document block': withTurn('user', { type: 'document', source: { type: 'text', media_type: 'text/plain', data: 'x' } }),
    'a server tool block': withTurn('assistant', { type: 'server_tool_use', id: 'srvtoolu_1', name: 'web_search', input: {} }),
    'citations on a user text block': withTurn('user', { type: 'text', text: 'x', citations: null }),
    'citations that are not null': withTurn('assistant', { type: 'text', text: 'x', citations: [] }),
    'a fifth marker, counted across the system, the tools and the turns': body({ tools: TOOLS.map(t => ({ ...t, cache_control: mark })).slice(0, 3)
      .concat(TOOLS.slice(3).map(({ cache_control, ...t }) => t)) }),
    'an assistant turn last (a prefill)': body({ messages: LOOP.slice(0, 2) }),
    'no thinking disabled': body({ thinking: { type: 'disabled' } }),
    'no budget_tokens': body({ thinking: { type: 'enabled', budget_tokens: 4000 } }),
    'no between_tools thinking': body({ thinking: { type: 'between_tools' } }),
  };
  for (const [why, payload] of Object.entries(refusals)) {
    assert.equal(admit(payload, env).status, 400, why);
  }
  // Four markers are admitted (the last tool, the system and two in the turns); five are not.
  const five = body({ messages: [...LOOP.slice(0, -1), { role: 'user', content: LOOP.at(-1).content.map(b => ({ ...b, cache_control: mark })) }] });
  assert.equal(admit(five, env).status, 400, 'five: three in the last turn');
  const exactlyFour = body({ messages: [{ ...LOOP[0], content: [{ ...LOOP[0].content[0], cache_control: mark }, LOOP[0].content[1]] }, ...LOOP.slice(1)] });
  assert.equal(admit(exactlyFour, env).model, 'claude-sonnet-5-5');
});

test('text-only requests keep exactly their admission', () => {
  const env = settings();
  const plain = { model: 'claude-opus-5-5', max_tokens: 16000, thinking: { type: 'adaptive' }, output_config: { effort: 'high' },
    system: [{ type: 'text', text: 'You diagnose.', cache_control: mark }], messages: [{ role: 'user', content: 'The family.' }] };
  assert.deepEqual(admit(plain, env), { model: 'claude-opus-5-5', price: { input: 4, cache_write: 5, cache_read: 0.2, output: 20 },
    maxTokens: 16000, stream: false });
  assert.equal(admit({ ...plain, messages: [{ role: 'user', content: 'q' }, { role: 'assistant', content: 'a' }, { role: 'user', content: 'q2' }] }, env).stream,
    false, 'text turns in both roles');
});

async function call(payload, answer, { env = settings(), gate = null, headers = {} } = {}) {
  gate = gate || createGate({ store: memoryStore(), env, now: () => NOW });
  const seen = [];
  const pending = [];
  const fetcher = async (url, init) => {
    seen.push({ url: String(url), init, held: gate.claudeStatus().inflight_usd });
    return typeof answer === 'function' ? answer() : answer;
  };
  const request = new Request('https://gw/v1/claude/messages', { method: 'POST', body: JSON.stringify(payload),
    headers: { Authorization: `Bearer ${TOKEN}`, ...headers } });
  const response = await route(request, env, { gate, fetcher, now: () => NOW, waitUntil: promise => pending.push(promise) });
  return { response, seen, gate, pending, bytes: new TextEncoder().encode(JSON.stringify(payload)).length };
}

test('the reservation is the worst case of the whole body: every tool and every turn are counted', async () => {
  const out = await call(body(), () => new Response('{}', { status: 400 }));
  assert.equal(out.seen[0].held, formatUsdMicro(worstCase(SONNET, out.bytes, 16000)));
  assert.deepEqual(JSON.parse(out.seen[0].init.body), body(), 'forwarded as sent');
  // An added tool and an added turn each grow the hold by exactly their bytes at the cache-write rate.
  const size = payload => new TextEncoder().encode(JSON.stringify(payload)).length;
  const extraTool = { name: 'extra', description: 'x'.repeat(4000), input_schema: { type: 'object' } };
  const withTool = body({ tools: [extraTool, ...TOOLS] });
  const tool = await call(withTool, () => new Response('{}', { status: 400 }));
  assert.equal(tool.seen[0].held, formatUsdMicro(worstCase(SONNET, size(withTool), 16000)));
  assert.equal(size(withTool) - size(body()), JSON.stringify(extraTool).length + 1);
  const turns = [...LOOP, { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_01D', name: 'read_run', input: { run_id: 'run-1' } }] },
    { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_01D', content: 'y'.repeat(12000) }] }];
  const longer = body({ messages: turns });
  const loop = await call(longer, () => new Response('{}', { status: 400 }));
  assert.equal(loop.seen[0].held, formatUsdMicro(worstCase(SONNET, size(longer), 16000)));
  assert.ok(worstCase(SONNET, size(longer), 16000) - worstCase(SONNET, size(body()), 16000) >= BigInt(Math.floor(12000 * 2.5)),
    'twelve thousand bytes of a result are held at $2.50 a million');
  // A body whose worst case does not fit the funded total is refused before anything is sent.
  const tight = await call(body(), () => new Response('{}', { status: 200 }), { env: settings({ CLAUDE_USD: '0.10' }) });
  assert.equal(tight.response.status, 402);
  assert.equal(tight.seen.length, 0);
});

test('a streamed tool_use answer passes through and settles at its usage, as an end_turn does', async () => {
  const usage = { input_tokens: 1200, cache_creation_input_tokens: 23000, cache_read_input_tokens: 14500, output_tokens: 1 };
  const events = [
    { type: 'message_start', message: { id: 'msg_t', type: 'message', role: 'assistant', model: 'claude-sonnet-5-5', content: [], stop_reason: null, usage } },
    { type: 'content_block_start', index: 0, content_block: { type: 'thinking', thinking: '' } },
    { type: 'content_block_delta', index: 0, delta: { type: 'thinking_delta', thinking: 'The trade count is thin.' } },
    { type: 'content_block_delta', index: 0, delta: { type: 'signature_delta', signature: SIGNATURE } },
    { type: 'content_block_stop', index: 0 },
    { type: 'content_block_start', index: 1, content_block: { type: 'tool_use', id: 'toolu_01E', name: 'gym_run', input: {}, caller: { type: 'direct' } } },
    { type: 'content_block_delta', index: 1, delta: { type: 'input_json_delta', partial_json: '{"hold": tr' } },
    { type: 'content_block_delta', index: 1, delta: { type: 'input_json_delta', partial_json: 'ue, "note": "nothing new"}' } },
    { type: 'content_block_stop', index: 1 },
    { type: 'message_delta', delta: { stop_reason: 'tool_use', stop_sequence: null }, usage: { output_tokens: 2400 } },
    { type: 'message_stop' },
  ];
  const text = events.map(e => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join('');
  const upstream = new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(text)); c.close(); } }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  const out = await call(body(), upstream, { headers: { 'X-LTCM-Role': 'researcher', 'X-LTCM-Request': 'swarm:condor:c5:m0:ab' } });
  const relayed = await out.response.text();
  await Promise.all(out.pending);
  assert.ok(relayed.startsWith(text), 'every byte of the tool call, unchanged');
  // 1,200 x $2 + 23,000 x $2.50 + 14,500 x $0.20 + 2,400 x $10, per million: 0.0024 + 0.0575 + 0.0029 + 0.024 = $0.0868.
  const parser = sseParser();
  const tail = [...parser.push(new TextEncoder().encode(relayed)), ...parser.end()].at(-1);
  assert.deepEqual(tail, { type: 'ltcm.cost', cost_usd: '0.086800', known: true, stop: 'tool_use' });
  const meter = out.gate.claudeStatus();
  assert.deepEqual([meter.spent_usd, meter.inflight_usd, meter.stops, meter.by_role], ['0.086800', '0.000000', { tool_use: 1 }, { researcher: '0.086800' }]);
  assert.deepEqual(out.gate.claudeRequest('swarm:condor:c5:m0:ab'), { request: 'swarm:condor:c5:m0:ab', state: 'settled', cost_usd: '0.086800' });
});

test('what leaves is the body that was checked: a key given twice reaches Anthropic with the value admission read', async () => {
  // JSON.parse keeps a repeated key's LAST value; a parser that kept the first would run the dearer model at 128K output
  // while the gateway priced Sonnet 5.5 at 16,000. The gateway forwards its own serialization of the checked parse.
  const raw = JSON.stringify(body()).replace('{"model":"claude-sonnet-5-5","max_tokens":16000,',
    '{"model":"claude-opus-5-5","max_tokens":128000,"model":"claude-sonnet-5-5","max_tokens":16000,');
  assert.ok(raw.includes('"max_tokens":128000'));
  const env = settings();
  const gate = createGate({ store: memoryStore(), env, now: () => NOW });
  const seen = [];
  const fetcher = async (url, init) => {
    seen.push({ init, held: gate.claudeStatus().inflight_usd });
    return new Response('{}', { status: 400 });
  };
  const request = new Request('https://gw/v1/claude/messages', { method: 'POST', body: raw, headers: { Authorization: `Bearer ${TOKEN}` } });
  await route(request, env, { gate, fetcher, now: () => NOW });
  const sent = seen[0].init.body;
  assert.equal(sent, JSON.stringify(JSON.parse(raw)), 'the checked parse, serialized');
  assert.ok(!sent.includes('claude-opus-5-5') && !sent.includes('128000'), 'the first values never leave');
  assert.equal(seen[0].held, formatUsdMicro(worstCase(SONNET, new TextEncoder().encode(sent).length, 16000)), 'held for the bytes sent');
});

test('a cost above its own hold is an overrun: booked in full and counted in the health report', () => {
  const env = settings();
  const gate = createGate({ store: memoryStore(), env, now: () => NOW });
  const held = gate.claudeReserve({ micro: '400000', request: 'swarm:condor:c6:m0:ab', at: NOW });
  assert.equal(held.ok, true);
  gate.claudeSettle({ id: held.id, reserved: held.micro, actual: '450000', role: 'researcher', stop: 'tool_use', at: NOW });
  const within = gate.claudeReserve({ micro: '400000', at: NOW });
  gate.claudeSettle({ id: within.id, reserved: within.micro, actual: '90000', role: 'researcher', stop: 'tool_use', at: NOW });
  const status = gate.claudeStatus(NOW);
  assert.deepEqual([status.overruns, status.overrun_usd, status.spent_usd], [1, '0.050000', '0.540000']);
});
