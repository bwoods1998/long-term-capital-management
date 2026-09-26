// Claude, behind a funded meter (Sept 26, 2026, the swarm sprint's B3).
//
// The owner funded the Anthropic account with $100 and placed its key here as CLAUDE_API_KEY, the
// same way the OpenAI key lives here: the House can ask for a Claude call, it cannot spend. The rule
// is CLAUDE_USD, the owner's FUNDED TOTAL (not a monthly allowance): every call ever metered here
// counts against it, and nothing resets it. A call is priced twice, as the frontier's are
// (lib/frontier.mjs). Before it leaves, at its worst case -- every input token a 5-minute cache write,
// the dearest an input token can be, and every allowed output token used (thinking is output, and
// `max_tokens` bounds it) -- and that much is reserved; a call whose worst case does not fit in what
// is left of the funded total is refused. After it returns, from Anthropic's own usage block, with
// uncached input, cache writes, cache reads and output each at its own rate. A model with no price in
// CLAUDE_MODELS is refused: the table is the allowlist.
//
// Anthropic's Messages API differs from OpenAI's Responses API in ways the meter must know
// (platform.claude.com/docs, read Sept 26, 2026): `usage.input_tokens` is the UNCACHED remainder only,
// and the cache's tokens are reported beside it (`cache_creation_input_tokens`,
// `cache_read_input_tokens`); a refusal is an HTTP 200 with `stop_reason: "refusal"` and is billed at
// its usage; thinking cannot be disabled on Claude Opus 5.5 and is controlled by
// `output_config.effort`. Fast mode (`speed`), US-only inference (`inference_geo`), tools and every
// other surface that bills beyond what this body shows are refused rather than trusted.

import { parseUsdMicro } from './money.mjs';

export const HOST = 'https://api.anthropic.com';
export const PATH = '/v1/messages';
export const API_VERSION = '2023-06-01';
//: The most output one call may ask for. Non-streaming calls above it risk an HTTP timeout before the
//: answer comes back (a House read is 600 seconds); the reservation is sized from the `max_tokens` admitted.
export const MAX_TOKENS = 16000;
//: The most a STREAMED call may ask for (Sept 27, 2026): its events flow as they are made, so no hop waits in silence
//: (a non-streamed high-effort answer ran past Cloudflare's 100-second wait in front of api.anthropic.com: HTTP 524).
export const MAX_TOKENS_STREAM = 32000;
//: A streamed call is cut after this long: just above the House's own 600-second limit, so the House gives up first.
export const STREAM_TIMEOUT_MS = 660000;
//: The largest request body read (a 1M-token context is not needed by any role; this bounds the reservation too).
export const MAX_REQUEST_BYTES = 1024 * 1024;
export const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'];
const MODEL_ID = /^claude-[a-z0-9-]{1,60}$/;
//: The House's id for one call (`X-LTCM-Request`), under which the gateway records what became of it.
export const REQUEST_HEADER = 'X-LTCM-Request';
const REQUEST_ID = /^[A-Za-z0-9:._-]{1,160}$/;
//: A hold with no settlement this long after it was made is released to zero: every call answers or is cut off within
//: ten minutes (570 s here, 600 s at the House), so only a Worker that died between reserve and settle leaves one.
export const STALE_HOLD_MS = 30 * 60 * 1000;
//: How many of the House's requests the meter remembers the outcome of.
export const RECENT_REQUESTS = 256;
//: Anthropic accepts at most four cache breakpoints a request.
const MAX_BREAKPOINTS = 4;

/** A House request id as the meter keeps it, or null. */
export function requestId(value) {
  return typeof value === 'string' && REQUEST_ID.test(value) ? value : null;
}

/**
 * `{ model: { input, cache_write, cache_read, output, geo? } }` in dollars per million tokens, from `CLAUDE_MODELS`. A
 * row that does not read (a rate missing, not finite, a cache write below the input rate, a cache read above it) is
 * absent, and its model is refused. `cache_write` is the 5-minute write rate, the only one admitted. `geo`, optional,
 * multiplies every rate of a call Anthropic says ran in that inference geography (`usage.inference_geo`, e.g.
 * `{"us": 1.1}`); a multiplier below 1 or that does not read is left out, and without one the rates stand.
 */
export function priceTable(env = {}) {
  let table;
  try {
    table = JSON.parse(env.CLAUDE_MODELS || '{}');
  } catch {
    return {};
  }
  if (!table || typeof table !== 'object' || Array.isArray(table)) return {};
  const out = {};
  for (const [model, row] of Object.entries(table)) {
    if (!MODEL_ID.test(model) || !row || typeof row !== 'object' || Array.isArray(row)) continue;
    const input = Number(row.input), write = Number(row.cache_write), read = Number(row.cache_read), output = Number(row.output);
    if (![input, write, read, output].every(Number.isFinite)) continue;
    if (!(input > 0 && output > 0 && write >= input && read >= 0 && read <= input)) continue;
    const geo = {};
    if (row.geo && typeof row.geo === 'object' && !Array.isArray(row.geo)) {
      for (const [name, factor] of Object.entries(row.geo)) {
        if (/^[a-z0-9_-]{1,16}$/.test(name) && Number.isFinite(Number(factor)) && Number(factor) >= 1) geo[name] = Number(factor);
      }
    }
    out[model] = { input, cache_write: write, cache_read: read, output, ...(Object.keys(geo).length ? { geo } : {}) };
  }
  return out;
}

/** The owner's funded total in micro-dollars (CLAUDE_USD); 0 when unset or unreadable, which refuses every call. */
export function capMicro(env = {}) {
  return parseUsdMicro(env.CLAUDE_USD, 0n);
}

const micro = dollars => BigInt(Math.ceil(dollars * 1e6));

/** The dearest geography multiplier a row names (1 without one): the worst case assumes it. */
const dearestGeo = price => Math.max(1, ...Object.values(price.geo || {}));

/** The most this call can cost, in micro-dollars: a byte per possible input token plus framing, all written to the cache. */
export function worstCase(price, bodyBytes, maxTokens) {
  const inputTokens = bodyBytes + 4096;
  return micro(dearestGeo(price) * (inputTokens * price.cache_write + maxTokens * price.output) / 1e6);
}

const count = value => {
  if (value === undefined || value === null) return 0;
  const n = Number(value);
  return Number.isSafeInteger(n) && n >= 0 ? n : null;
};

/**
 * What the call did cost, from Anthropic's usage block, in micro-dollars; null when the block does not read.
 * `input_tokens` is the uncached remainder; cache writes and reads are separate counts, each at its own rate. A write
 * the usage says went to the one-hour cache (never asked for here) is priced at twice the input rate, its list price.
 */
export function actualCost(price, usage) {
  if (!usage || typeof usage !== 'object' || Array.isArray(usage)) return null;
  const input = count(usage.input_tokens), output = count(usage.output_tokens);
  const written = count(usage.cache_creation_input_tokens), read = count(usage.cache_read_input_tokens);
  if (input === null || output === null || written === null || read === null
      || usage.input_tokens === undefined || usage.output_tokens === undefined) return null;
  const hour = Math.min(written, count(usage.cache_creation?.ephemeral_1h_input_tokens) ?? 0);
  const geo = typeof usage.inference_geo === 'string' && Object.hasOwn(price.geo || {}, usage.inference_geo) ? price.geo[usage.inference_geo] : 1;
  return micro(geo * (input * price.input + (written - hour) * price.cache_write + hour * Math.max(price.cache_write, 2 * price.input)
    + read * price.cache_read + output * price.output) / 1e6);
}

/** A cache marker as this gateway admits it: ephemeral, five minutes (the default or said so). */
function cacheMark(mark) {
  if (mark === undefined) return 0;
  if (!mark || typeof mark !== 'object' || Array.isArray(mark) || mark.type !== 'ephemeral'
      || Object.keys(mark).some(key => !['type', 'ttl'].includes(key)) || (mark.ttl !== undefined && mark.ttl !== '5m')) return null;
  return 1;
}

/** Text content: a string, or 1-16 text blocks that may carry a cache marker. The number of markers, or null. */
function textBlocks(content, { allowString = true } = {}) {
  if (typeof content === 'string') return allowString ? 0 : null;
  if (!Array.isArray(content) || content.length < 1 || content.length > 16) return null;
  let marks = 0;
  for (const block of content) {
    if (!block || typeof block !== 'object' || Array.isArray(block) || block.type !== 'text' || typeof block.text !== 'string'
        || Object.keys(block).some(key => !['type', 'text', 'cache_control'].includes(key))) return null;
    const mark = cacheMark(block.cache_control);
    if (mark === null) return null;
    marks += mark;
  }
  return marks;
}

function outputConfigValid(config) {
  if (config === undefined) return true;
  if (!config || typeof config !== 'object' || Array.isArray(config) || Object.keys(config).some(key => !['effort', 'format'].includes(key))) return false;
  if (config.effort !== undefined && !EFFORTS.includes(config.effort)) return false;
  const format = config.format;
  if (format !== undefined && (!format || typeof format !== 'object' || Array.isArray(format) || format.type !== 'json_schema'
      || !format.schema || typeof format.schema !== 'object' || Array.isArray(format.schema)
      || Object.keys(format).some(key => !['type', 'schema'].includes(key)))) return false;
  return true;
}

/**
 * Check a request body before it is sent: `{ model, price, maxTokens, stream }` or `{ error, status }`. Only inline
 * text, adaptive thinking, an effort and a JSON-schema answer format are admitted, and an assistant turn last is
 * refused (Anthropic refuses a prefill). `stream: true` (Sept 27, 2026) is metered from the event stream itself
 * (`StreamMeter`) and may ask for up to MAX_TOKENS_STREAM.
 */
export function admit(body, env = {}) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { error: 'The request must be a JSON object.', status: 400 };
  const model = String(body.model || '');
  const table = priceTable(env);
  const row = MODEL_ID.test(model) && Object.hasOwn(table, model) ? table[model] : null;
  if (!row) return { error: `No price is configured for model "${model}"; an unpriced call is refused.`, status: 403 };
  if (body.stream !== undefined && typeof body.stream !== 'boolean') return { error: 'stream is true or false.', status: 400 };
  const stream = body.stream === true;
  const allowed = new Set(['model', 'max_tokens', 'system', 'messages', 'thinking', 'output_config', 'stream']);
  const extra = Object.keys(body).filter(key => !allowed.has(key));
  if (extra.length) {
    return { error: `Only inline text with adaptive thinking is priced by this gateway; refused: ${extra.slice(0, 4).join(', ')}.`, status: 400 };
  }
  let marks = 0;
  if (body.system !== undefined) {
    const found = textBlocks(body.system);
    if (found === null) return { error: 'The system prompt must be a string or text blocks.', status: 400 };
    marks += found;
  }
  const messages = body.messages;
  if (!Array.isArray(messages) || messages.length < 1 || messages.length > 64) {
    return { error: 'messages must hold 1 to 64 turns.', status: 400 };
  }
  for (const turn of messages) {
    if (!turn || typeof turn !== 'object' || Array.isArray(turn) || !['user', 'assistant'].includes(turn.role)
        || Object.keys(turn).some(key => !['role', 'content'].includes(key))) {
      return { error: 'Each turn is a user or assistant role with text content.', status: 400 };
    }
    const found = textBlocks(turn.content);
    if (found === null) return { error: 'Each turn is a user or assistant role with text content.', status: 400 };
    marks += found;
  }
  if (messages.at(-1).role !== 'user') return { error: 'The last turn must be the user\'s: an assistant prefill is refused.', status: 400 };
  if (marks > MAX_BREAKPOINTS) return { error: `At most ${MAX_BREAKPOINTS} five-minute cache breakpoints are admitted.`, status: 400 };
  const thinking = body.thinking;
  if (thinking !== undefined && (!thinking || typeof thinking !== 'object' || Array.isArray(thinking) || thinking.type !== 'adaptive'
      || Object.keys(thinking).some(key => !['type', 'display'].includes(key))
      || (thinking.display !== undefined && !['omitted', 'summarized'].includes(thinking.display)))) {
    return { error: 'thinking must be absent or adaptive: Claude Opus 5.5 cannot disable it, and effort is the control.', status: 400 };
  }
  if (!outputConfigValid(body.output_config)) {
    return { error: `output_config takes an effort (${EFFORTS.join(', ')}) and a json_schema format, nothing else.`, status: 400 };
  }
  const maxTokens = body.max_tokens;
  const ceiling = stream ? MAX_TOKENS_STREAM : MAX_TOKENS;
  if (!Number.isInteger(maxTokens) || maxTokens < 1 || maxTokens > ceiling) {
    return { error: `max_tokens is required, between 1 and ${ceiling}${stream ? '' : ` (${MAX_TOKENS_STREAM} when streamed)`}.`, status: 400 };
  }
  return { model, price: row, maxTokens, stream };
}

/**
 * Server-sent events, read incrementally: `push(bytes)` returns the events its bytes completed, `end()` whatever the
 * stream's end completes. An event is its parsed `data` JSON (Anthropic's carry their own `type`), or
 * `{ type: 'unreadable' }` when its data is not JSON.
 */
export function sseParser() {
  const decoder = new TextDecoder();
  let buffer = '';
  const parse = block => {
    const data = block.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).replace(/^ /, '')).join('\n');
    if (!data) return null;
    try {
      const value = JSON.parse(data);
      return value && typeof value === 'object' && !Array.isArray(value) ? value : { type: 'unreadable' };
    } catch {
      return { type: 'unreadable' };
    }
  };
  const drain = () => {
    const out = [];
    for (let at = buffer.search(/\r?\n\r?\n/); at >= 0; at = buffer.search(/\r?\n\r?\n/)) {
      const block = buffer.slice(0, at);
      buffer = buffer.slice(at).replace(/^\r?\n\r?\n/, '');
      const event = parse(block);
      if (event) out.push(event);
    }
    return out;
  };
  return {
    push(bytes) {
      buffer += decoder.decode(bytes, { stream: true });
      return drain();
    },
    end() {
      buffer += decoder.decode();
      const out = drain();
      const event = buffer.trim() ? parse(buffer) : null;
      buffer = '';
      return event ? [...out, event] : out;
    },
  };
}

/**
 * What one streamed answer used, read from its events: input and cache usage from `message_start`, output from the
 * last `message_delta` (its usage is cumulative, and any count it carries replaces the start's), the stop reason, an
 * `error` event, and whether `message_stop` came.
 */
export class StreamMeter {
  constructor() {
    this.started = false;
    this.stopped = false;
    this.usage = {};
    this.stop = null;
    this.error = null;
  }

  observe(event) {
    if (!event || typeof event !== 'object') return;
    const merge = usage => {
      if (usage && typeof usage === 'object' && !Array.isArray(usage)) {
        for (const [key, value] of Object.entries(usage)) if (value !== null && value !== undefined) this.usage[key] = value;
      }
    };
    if (event.type === 'message_start') {
      this.started = true;
      merge(event.message?.usage);
    } else if (event.type === 'message_delta') {
      merge(event.usage);
      if (typeof event.delta?.stop_reason === 'string') this.stop = event.delta.stop_reason;
    } else if (event.type === 'message_stop') {
      this.stopped = true;
    } else if (event.type === 'error') {
      this.error = typeof event.error?.type === 'string' ? event.error.type : 'error';
    }
  }

  get geo() {
    return typeof this.usage.inference_geo === 'string' ? this.usage.inference_geo : null;
  }

  /**
   * `{ cost, stop }`: the cost in micro-dollars, or null when it is unknown (the whole hold stays spent). A complete
   * answer settles at its usage. An `error` event settles at the usage seen so far, or unknown before `message_start`.
   * A stream that broke, or ended without `message_stop`, is unknown: the call ran and may be billed.
   */
  settlement(price, { broken = false } = {}) {
    const cost = () => (this.started ? actualCost(price, this.usage) : null);
    if (this.stopped && !this.error) return { cost: cost(), stop: this.stop || 'end_turn' };
    if (this.error) return { cost: cost(), stop: 'stream_error' };
    return { cost: null, stop: broken ? 'stream_broken' : 'stream_cut' };
  }
}
