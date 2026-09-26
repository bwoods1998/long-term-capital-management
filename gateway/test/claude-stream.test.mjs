// Streamed Claude calls through the gateway (Sept 27, 2026): Anthropic's events pass straight through to the House as
// they arrive, are metered on the way, and are settled when the stream ends (under waitUntil), with one `ltcm.cost`
// event last. No network: a ReadableStream stands in for Anthropic's answer.
import test from 'node:test';
import assert from 'node:assert/strict';
import { admit, sseParser, StreamMeter, worstCase, MAX_TOKENS_STREAM } from '../lib/claude.mjs';
import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { formatUsdMicro } from '../lib/money.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const KEY = 'anthropic-test-key-never-leaves-the-worker';
const OPUS = { input: 4, cache_write: 5, cache_read: 0.2, output: 20 };
const MODELS = JSON.stringify({ 'claude-opus-5-5': OPUS });
const settings = extra => ({ GATEWAY_TOKEN: TOKEN, CLAUDE_API_KEY: KEY, CLAUDE_USD: '100', CLAUDE_MODELS: MODELS, ...extra });
const NOW = Date.parse('2026-09-27T16:00:00Z');

const body = (extra = {}) => ({
  model: 'claude-opus-5-5', max_tokens: 32000, stream: true, thinking: { type: 'adaptive', display: 'summarized' },
  output_config: { effort: 'high' }, system: [{ type: 'text', text: 'You are the architect.', cache_control: { type: 'ephemeral' } }],
  messages: [{ role: 'user', content: 'Propose new families.' }], ...extra,
});
const START = { type: 'message_start', message: { id: 'msg_1', type: 'message', role: 'assistant', model: 'claude-opus-5-5', content: [],
  stop_reason: null, usage: { input_tokens: 2000, cache_creation_input_tokens: 10000, cache_read_input_tokens: 30000, output_tokens: 1 } } };
const EVENTS = [
  START,
  { type: 'content_block_start', index: 0, content_block: { type: 'thinking', thinking: '' } },
  { type: 'content_block_delta', index: 0, delta: { type: 'thinking_delta', thinking: 'Weighing the trend days.' } },
  { type: 'content_block_stop', index: 0 },
  { type: 'ping' },
  { type: 'content_block_start', index: 1, content_block: { type: 'text', text: '' } },
  { type: 'content_block_delta', index: 1, delta: { type: 'text_delta', text: '{"families":' } },
  { type: 'content_block_delta', index: 1, delta: { type: 'text_delta', text: ' []}' } },
  { type: 'content_block_stop', index: 1 },
  { type: 'message_delta', delta: { stop_reason: 'end_turn', stop_sequence: null }, usage: { output_tokens: 6000 } },
  { type: 'message_stop' },
];
const sse = events => events.map(event => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`).join('');
// 2,000 x $4 + 10,000 x $5 + 30,000 x $0.20 + 6,000 x $20, per million: $0.184.
const COST = '0.184000';

/** Anthropic's streamed answer: `text` in `chunk`-byte pieces, erroring after `breakAfter` pieces, waiting on `hold`. */
function upstream(text, { chunk = 37, breakAfter = null, hold = null, status = 200 } = {}) {
  const bytes = new TextEncoder().encode(text);
  const state = { at: 0, sent: 0, cancelled: false };
  const stream = new ReadableStream({
    async pull(controller) {
      if (hold && state.sent === 1) await hold;
      if (breakAfter !== null && state.sent >= breakAfter) return controller.error(new Error('connection reset'));
      if (state.at >= bytes.length) return controller.close();
      controller.enqueue(bytes.slice(state.at, state.at + chunk));
      state.at += chunk;
      state.sent += 1;
    },
    cancel() { state.cancelled = true; },
  });
  return { response: new Response(stream, { status, headers: { 'Content-Type': 'text/event-stream' } }), state };
}

const ask = (payload, headers = {}) => new Request('https://gw/v1/claude/messages', {
  method: 'POST', body: JSON.stringify(payload), headers: { Authorization: `Bearer ${TOKEN}`, ...headers },
});

async function call(payload, answer, { env = settings(), gate = null, headers = {} } = {}) {
  gate = gate || createGate({ store: memoryStore(), env, now: () => NOW });
  const seen = [];
  const pending = [];
  const fetcher = async (url, init) => {
    seen.push({ url: String(url), init, held: gate.claudeStatus().inflight_usd });
    if (answer instanceof Error) throw answer;
    return typeof answer === 'function' ? answer() : answer;
  };
  const response = await route(ask(payload, headers), env, { gate, fetcher, now: () => NOW, waitUntil: promise => pending.push(promise) });
  return { response, seen, gate, pending, bytes: new TextEncoder().encode(JSON.stringify(payload)).length };
}

/** The `ltcm.cost` event at the end of a stream the gateway relayed. */
const tail = text => {
  const events = [];
  const parser = sseParser();
  events.push(...parser.push(new TextEncoder().encode(text)), ...parser.end());
  return events.at(-1).type === 'ltcm.cost' ? events.at(-1) : null;
};

test('admission: a streamed call may ask for up to 32,000 tokens; an unstreamed one still 16,000', () => {
  const env = settings();
  assert.deepEqual(admit(body(), env), { model: 'claude-opus-5-5', price: OPUS, maxTokens: 32000, stream: true });
  assert.equal(MAX_TOKENS_STREAM, 32000);
  assert.equal(admit(body({ max_tokens: 32001 }), env).status, 400);
  assert.equal(admit(body({ stream: false, max_tokens: 16001 }), env).status, 400);
  assert.equal(admit(body({ stream: false, max_tokens: 16000 }), env).stream, false);
  assert.equal(admit(body({ stream: 'yes' }), env).status, 400);
});

test('the stream passes straight through as it arrives, is metered from its events and settled when it ends', async () => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const anthropic = upstream(sse(EVENTS), { hold: gate });
  const out = await call(body(), anthropic.response, { headers: { 'X-LTCM-Role': 'architect', 'X-LTCM-Request': 'swarm:architect:1:ab' } });
  assert.equal(out.response.status, 200);
  assert.equal(out.response.headers.get('Content-Type'), 'text/event-stream; charset=utf-8');
  assert.equal(out.seen[0].url, 'https://api.anthropic.com/v1/messages');
  assert.equal(out.seen[0].init.headers.Accept, 'text/event-stream');
  assert.equal(out.seen[0].init.headers['x-api-key'], KEY);
  assert.equal(JSON.parse(out.seen[0].init.body).stream, true);
  assert.equal(out.seen[0].held, formatUsdMicro(worstCase(OPUS, out.bytes, 32000)), 'held at the 32,000-token worst case');
  // The first bytes reach the House while Anthropic is still working: nothing waits for the end.
  const reader = out.response.body.getReader();
  const first = new TextDecoder().decode((await reader.read()).value);
  assert.ok(sse(EVENTS).startsWith(first) && first.length > 0);
  assert.equal(out.gate.claudeStatus().inflight_usd, formatUsdMicro(worstCase(OPUS, out.bytes, 32000)), 'still held mid-stream');
  release();
  let text = first;
  for (let part = await reader.read(); !part.done; part = await reader.read()) text += new TextDecoder().decode(part.value);
  await Promise.all(out.pending);
  assert.ok(text.startsWith(sse(EVENTS)), 'every byte of Anthropic\'s stream, unchanged');
  assert.deepEqual(tail(text), { type: 'ltcm.cost', cost_usd: COST, known: true, stop: 'end_turn' });
  const meter = out.gate.claudeStatus();
  assert.deepEqual([meter.spent_usd, meter.inflight_usd, meter.calls, meter.stops, meter.by_role],
    [COST, '0.000000', 1, { end_turn: 1 }, { architect: COST }]);
  assert.deepEqual(out.gate.claudeRequest('swarm:architect:1:ab'), { request: 'swarm:architect:1:ab', state: 'settled', cost_usd: COST });
  assert.ok(!text.includes(KEY));
});

test('a stream that breaks after its headers, or ends without message_stop, keeps its whole hold', async () => {
  for (const [answer, stop] of [[() => upstream(sse(EVENTS), { breakAfter: 5 }).response, 'stream_broken'],
    [() => upstream(sse(EVENTS.slice(0, 7))).response, 'stream_cut']]) {
    const out = await call(body(), answer, { headers: { 'X-LTCM-Request': `cut-${stop}` } });
    const text = await out.response.text();
    await Promise.all(out.pending);
    const worst = formatUsdMicro(worstCase(OPUS, out.bytes, 32000));
    assert.deepEqual(tail(text), { type: 'ltcm.cost', cost_usd: worst, known: false, stop }, stop);
    assert.deepEqual([out.gate.claudeStatus().spent_usd, out.gate.claudeStatus().inflight_usd], [worst, '0.000000'], stop);
    assert.equal(out.gate.claudeRequest(`cut-${stop}`).state, 'unknown');
  }
});

test('an error event before any output settles at message_start\'s usage; before it, or once output began, unknown', async () => {
  const overloaded = { type: 'error', error: { type: 'overloaded_error', message: 'Overloaded' } };
  const input = await call(body(), upstream(sse([START, { type: 'ping' }, overloaded])).response);
  assert.deepEqual(tail(await input.response.text()), { type: 'ltcm.cost', cost_usd: '0.064020', known: true, stop: 'stream_error' });
  await Promise.all(input.pending);
  assert.equal(input.gate.claudeStatus().spent_usd, '0.064020', 'input, cache and the one output token message_start reported');
  for (const events of [[overloaded], [...EVENTS.slice(0, 7), overloaded]]) {
    const out = await call(body(), upstream(sse(events)).response);
    const text = await out.response.text();
    await Promise.all(out.pending);
    const worst = formatUsdMicro(worstCase(OPUS, out.bytes, 32000));
    assert.deepEqual(tail(text), { type: 'ltcm.cost', cost_usd: worst, known: false, stop: 'stream_error' }, `${events.length} events`);
    assert.equal(out.gate.claudeStatus().spent_usd, worst, 'unknown is not free: the whole hold stays');
  }
});

test('a House that goes away while Anthropic is quiet is noticed at once and settles at its whole hold', async () => {
  let release;
  const quiet = new Promise(resolve => { release = resolve; });
  const anthropic = upstream(sse(EVENTS), { hold: quiet });  // after its first piece, Anthropic says nothing
  const out = await call(body(), anthropic.response);
  const reader = out.response.body.getReader();
  await reader.read();
  await reader.cancel();
  await Promise.all(out.pending);  // settled without Anthropic sending another byte
  assert.equal(anthropic.state.cancelled, true);
  assert.deepEqual([out.gate.claudeStatus().spent_usd, out.gate.claudeStatus().stops],
    [formatUsdMicro(worstCase(OPUS, out.bytes, 32000)), { house_gone: 1 }]);
  release();
});

test('a House that goes away stops the stream, and the call settles unknown', async () => {
  const anthropic = upstream(sse(EVENTS), { chunk: 20 });
  const out = await call(body(), anthropic.response);
  const reader = out.response.body.getReader();
  await reader.read();
  await reader.cancel();
  await Promise.all(out.pending);
  assert.equal(anthropic.state.cancelled, true, 'Anthropic\'s stream is cancelled with it');
  const meter = out.gate.claudeStatus();
  assert.deepEqual([meter.spent_usd, meter.inflight_usd, meter.stops],
    [formatUsdMicro(worstCase(OPUS, out.bytes, 32000)), '0.000000', { house_gone: 1 }]);
});

test('an error answer to a streamed call, the kill switch and a lost request keep their unstreamed rules', async () => {
  const overloaded = await call(body(), new Response(JSON.stringify({ type: 'error', error: { type: 'overloaded_error' } }), { status: 529 }));
  assert.equal(overloaded.response.status, 529);
  assert.equal(overloaded.response.headers.get('X-LTCM-Cost-USD'), '0.000000');
  assert.equal((await overloaded.response.json()).error.type, 'overloaded_error');
  assert.equal(overloaded.pending.length, 0);

  const env = settings();
  const gate = createGate({ store: memoryStore(), env, now: () => NOW });
  gate.setKill(true);
  const killed = await call(body(), upstream(sse(EVENTS)).response, { env, gate });
  assert.equal(killed.response.status, 423);
  assert.equal(killed.seen.length, 0);

  const lost = await call(body(), new TypeError('network connection lost'));
  assert.equal(lost.response.status, 502);
  assert.equal(lost.gate.claudeStatus().spent_usd, '0.000000');
});

test('the SSE parser reads events split anywhere, CRLF endings, several data lines and data that is not JSON', () => {
  const parser = sseParser();
  const text = 'event: ping\r\ndata: {"type":"ping"}\r\n\r\n: a comment\n\nevent: x\ndata: {"type":\ndata: "message_stop"}\n\ndata: not json\n\n';
  const bytes = new TextEncoder().encode(text);
  const events = [];
  for (let at = 0; at < bytes.length; at += 3) events.push(...parser.push(bytes.slice(at, at + 3)));
  events.push(...parser.end());
  assert.deepEqual(events, [{ type: 'ping' }, { type: 'message_stop' }, { type: 'unreadable' }]);
  const meter = new StreamMeter();
  for (const event of EVENTS) meter.observe(event);
  assert.deepEqual(meter.settlement(OPUS), { cost: 184000n, stop: 'end_turn' });
  assert.equal(meter.usage.output_tokens, 6000, 'the delta\'s cumulative output replaces the start\'s');
});
