// The frontier model, behind a budget (Sept 19, 2026).
//
// The floor's agents run on cheap open models. A frontier model audits a candidate before it
// trades real money and, on a slow clock, writes new strategy code. Its key lives here and
// nowhere else, for the same reason the venue keys do: the trading VM can ask, it cannot spend.
//
// The rule is a monthly dollar budget the VM cannot raise. A call is priced twice. Before it
// leaves, at its worst case (every input token uncached, every allowed output token used), and
// that much is reserved; a call whose worst case does not fit in what is left of the month is
// refused. After it returns, at what the provider says it used, and the difference is given
// back. A model this module has no price for is refused: an unpriced call is an uncapped one.

import { parseUsdMicro } from './money.mjs';

export const HOST = 'https://api.openai.com';
export const PATH = '/v1/responses';
export const AGENT_HEADER = 'X-LTCM-Agent';
//: The role a call is made for (a slug). It names the call's output ceiling in `FRONTIER_ROLE_MAX_OUTPUT`.
export const ROLE_HEADER = 'X-LTCM-Role';
//: The most output one call may ask for, unless its role names another ceiling. The reservation is sized from it.
export const MAX_OUTPUT_TOKENS = 16000;
//: The most any role's ceiling may name: a larger number in `FRONTIER_ROLE_MAX_OUTPUT` is not read.
export const ROLE_MAX_OUTPUT_LIMIT = 128000;
const SLUG = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const RATE_FIELDS = ['input', 'cached', 'output', 'long_input', 'long_cached', 'long_output', 'uncached', 'long_uncached'];

/**
 * One row of rates, checked, or null. `base` is the standard row a flex row discounts (Sept 26, 2026 (the options-swarm
 * run, Wave 5)): a long-context rate the flex row leaves out is the standard one (the meter errs high), and no flex rate
 * may exceed its standard rate, so a flex call settled at flex rates never settles above the standard worst case it
 * reserved.
 */
function rates(row, base = null) {
  if (!row || typeof row !== 'object' || Array.isArray(row)) return null;
  const input = Number(row.input), cached = Number(row.cached ?? row.input), output = Number(row.output);
  const longInput = Number(row.long_input ?? base?.long_input ?? input), longCached = Number(row.long_cached ?? base?.long_cached ?? cached);
  const longOutput = Number(row.long_output ?? base?.long_output ?? output);
  // `input` is the cache-write rate, the dearest an input token can be. `uncached` is the
  // plain rate for a token neither read from nor written to the cache; absent, it is `input`,
  // so a table without it prices exactly as before.
  const uncached = Number(row.uncached ?? input), longUncached = Number(row.long_uncached ?? base?.long_uncached ?? longInput);
  if (![input, cached, output, longInput, longCached, longOutput, uncached, longUncached].every(Number.isFinite)
      || !(input > 0 && cached >= 0 && cached <= input && output > 0
        && longInput >= input && longCached >= cached && longCached <= longInput && longOutput >= output
        && uncached >= cached && uncached <= input && longUncached >= longCached && longUncached <= longInput && longUncached >= uncached)) {
    return null;
  }
  const out = { input, cached, output, long_input: longInput, long_cached: longCached, long_output: longOutput, uncached, long_uncached: longUncached };
  if (base && RATE_FIELDS.some(field => out[field] > base[field])) return null;
  return out;
}

/**
 * `{ model: { input, cached, output, ..., flex? } }` in dollars per million tokens, from `FRONTIER_MODELS`. A model whose
 * standard rates do not read is absent (refused). `flex` (Sept 26, 2026, Wave 5) is the model's flex-tier rates,
 * `{input, cached, output}` and optionally the long-context and uncached rates; a model without it, or whose flex rates
 * do not read, is priced as before and cannot be sent on the flex tier.
 */
export function priceTable(env = {}) {
  try {
    const table = JSON.parse(env.FRONTIER_MODELS || '{}');
    const out = {};
    for (const [model, row] of Object.entries(table)) {
      if (!/^[A-Za-z0-9._:-]{1,80}$/.test(model)) continue;
      const standard = rates(row);
      if (!standard) continue;
      const flex = row?.flex === undefined ? null : rates(row.flex, standard);
      out[model] = flex ? { ...standard, flex } : standard;
    }
    return out;
  } catch {
    return {};
  }
}

/** `FRONTIER_ROLE_MAX_OUTPUT` read: `{ role: ceiling }` for each slug with a whole number from 1 to the limit. */
export function roleCeilings(env = {}) {
  let table;
  try {
    table = JSON.parse(env.FRONTIER_ROLE_MAX_OUTPUT || '{}');
  } catch {
    return {};
  }
  if (!table || typeof table !== 'object' || Array.isArray(table)) return {};
  const out = {};
  for (const [role, value] of Object.entries(table)) {
    if (SLUG.test(role) && Number.isSafeInteger(value) && value >= 1 && value <= ROLE_MAX_OUTPUT_LIMIT) out[role] = value;
  }
  return out;
}

/**
 * The output ceiling of a call made for `role` (the `X-LTCM-Role` header): what `FRONTIER_ROLE_MAX_OUTPUT` names for it,
 * else MAX_OUTPUT_TOKENS. A role it does not name, a header that is not a slug, or none at all gets the default.
 */
export function outputCeiling(env = {}, role = null) {
  const table = roleCeilings(env);
  return typeof role === 'string' && SLUG.test(role) && Object.hasOwn(table, role) ? table[role] : MAX_OUTPUT_TOKENS;
}

/** A funded month expires instead of creating another allowance at the next UTC month boundary. */
export function monthCapMicro(env = {}, at = Date.now()) {
  if (Object.hasOwn(env, 'FRONTIER_FUNDED_MONTH')) {
    const funded = String(env.FRONTIER_FUNDED_MONTH);
    const time = new Date(at);
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(funded) || !Number.isFinite(time.getTime())
        || time.toISOString().slice(0, 7) !== funded) return 0n;
  }
  return parseUsdMicro(env.FRONTIER_MONTH_USD, 0n);
}

const micro = dollars => BigInt(Math.ceil(dollars * 1e6));

/** The most this call can cost, in micro-dollars. */
export function worstCase(price, bodyBytes, maxOutputTokens) {
  // Text-only requests; a byte per possible token plus framing, without guessing a tokenizer.
  const inputTokens = bodyBytes + 4096;
  return micro((inputTokens * (price.long_input ?? price.input) + maxOutputTokens * (price.long_output ?? price.output)) / 1e6);
}

/** What the call did cost, from the provider's own usage block; null when it carries none. */
export function actualCost(price, usage) {
  if (!usage || typeof usage !== 'object') return null;
  const input = Number(usage.input_tokens), output = Number(usage.output_tokens);
  if (!Number.isFinite(input) || !Number.isFinite(output) || input < 0 || output < 0) return null;
  const cached = Math.min(input, Math.max(0, Number(usage.input_tokens_details?.cached_tokens) || 0));
  // GPT-5.6 and later report the tokens a call wrote to the prompt cache, billed at 1.25x the
  // plain input rate; reads are 0.1x (developers.openai.com/api/docs/guides/prompt-caching,
  // read Sept 22, 2026). A usage block without the field prices every uncached token as a write.
  const reported = Number(usage.input_tokens_details?.cache_write_tokens);
  const written = Number.isFinite(reported) && reported >= 0 ? Math.min(input - cached, reported) : input - cached;
  const plain = input - cached - written;
  const long = input > 272000;
  return micro((written * (long ? price.long_input ?? price.input : price.input)
    + plain * (long ? price.long_uncached ?? price.long_input ?? price.input : price.uncached ?? price.input)
    + cached * (long ? price.long_cached ?? price.cached : price.cached)
    + output * (long ? price.long_output ?? price.output : price.output)) / 1e6);
}

/**
 * True for the one 5xx that is settled at zero: the provider's own capacity refusal, a 503 whose
 * body is OpenAI's error object of type `service_unavailable_error` ("the requested model does not
 * have enough capacity to process your request at the moment", developers.openai.com/api/docs/
 * guides/error-codes, read Sept 24, 2026). The request was turned away before any work, so there is
 * nothing to bill. Measured Sept 22, 2026: two such answers ("server_is_overloaded") each kept its
 * whole worst case on the month, $2.02 for one.
 *
 * Every other 5xx keeps its worst case, because unknown is not free: a 500 `server_error` can
 * come after the model has worked, and the same documentation says nothing of whether it bills;
 * a 502, a 504 or a 503 without that body is an edge or proxy answering for a call the provider
 * may still have received and billed.
 */
export function unprocessed(status, text) {
  if (status !== 503) return false;
  try {
    const error = JSON.parse(text)?.error;
    return !!error && typeof error === 'object' && !Array.isArray(error) && error.type === 'service_unavailable_error';
  } catch {
    return false;
  }
}

/** The prompt-cache hints OpenAI documents for the Responses API, and nothing else. */
const CACHE_KEY = /^[A-Za-z0-9._:-]{1,64}$/;
const RETENTION = new Set(['in_memory', '24h']);

function cacheHintsValid(body) {
  if (body.prompt_cache_key !== undefined && !(typeof body.prompt_cache_key === 'string' && CACHE_KEY.test(body.prompt_cache_key))) return false;
  if (body.prompt_cache_retention !== undefined && !RETENTION.has(body.prompt_cache_retention)) return false;
  const options = body.prompt_cache_options;
  if (options !== undefined) {
    // A prewarm writes the cache without an answer; nothing here needs one, so it is refused
    // rather than trusted to be metered like an ordinary call.
    if (!options || typeof options !== 'object' || Array.isArray(options)
        || Object.keys(options).some(key => !['mode', 'ttl', 'prewarm'].includes(key))
        || (options.mode !== undefined && !['implicit', 'explicit'].includes(options.mode))
        || (options.ttl !== undefined && options.ttl !== '30m')
        || (options.prewarm !== undefined && options.prewarm !== false)) return false;
  }
  return true;
}

/** An input message's content: a string, or text blocks that may mark an explicit cache breakpoint. */
function textContent(content) {
  if (typeof content === 'string') return 0;
  if (!Array.isArray(content) || content.length < 1 || content.length > 16) return null;
  let breakpoints = 0;
  for (const block of content) {
    if (!block || typeof block !== 'object' || block.type !== 'input_text' || typeof block.text !== 'string'
        || Object.keys(block).some(key => !['type', 'text', 'prompt_cache_breakpoint'].includes(key))) return null;
    if (block.prompt_cache_breakpoint !== undefined) {
      const mark = block.prompt_cache_breakpoint;
      if (!mark || typeof mark !== 'object' || Array.isArray(mark) || Object.keys(mark).length !== 1 || mark.mode !== 'explicit') return null;
      breakpoints += 1;
    }
  }
  return breakpoints;
}

/**
 * Check a request body before it is sent. `{ model, price, flex, maxOutput, ceiling }` or `{ error, status }`.
 * Streaming and background calls are refused: the usage block that settles the bill arrives
 * with a complete response, and a call that outlives the request cannot be settled at all.
 * `flex` is the model's flex rates when the call asks for the flex tier, else null; the call is
 * still reserved at `price`, the standard rates, because OpenAI may serve it on another tier.
 */
export function admit(body, env, { role = null } = {}) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { error: 'The request must be a JSON object.', status: 400 };
  const model = String(body.model || '');
  const price = priceTable(env)[model];
  if (!price) return { error: `No price is configured for model "${model}"; an unpriced call is refused.`, status: 403 };
  if (body.stream === true || body.background === true) return { error: 'Streaming and background calls cannot be metered and are refused.', status: 400 };
  // The meter prices only inline text and standard inference. A stored conversation, image,
  // paid built-in tool or faster service tier could bill work that is absent from this body.
  // Prompt-cache hints change what a call costs only through the usage block the bill is settled
  // from (cache reads are cheaper, writes are priced at `input`), so they are admitted, bounded.
  const allowed = new Set(['model', 'input', 'max_output_tokens', 'reasoning', 'stream', 'background', 'service_tier',
    'prompt_cache_key', 'prompt_cache_retention', 'prompt_cache_options']);
  let breakpoints = 0;
  const textInput = typeof body.input === 'string' || (Array.isArray(body.input) && body.input.every(item => {
    if (!item || typeof item !== 'object' || !['system', 'developer', 'user', 'assistant'].includes(item.role)
        || !Object.keys(item).every(key => ['role', 'content'].includes(key))) return false;
    // Assistant turns stay plain strings: output blocks are a different type, and none is needed.
    const marks = item.role === 'assistant' ? (typeof item.content === 'string' ? 0 : null) : textContent(item.content);
    if (marks === null) return false;
    breakpoints += marks;
    return true;
  }));
  // Flex (Sept 26, 2026 (the options-swarm run, Wave 5)): half price, slower, and refused with a 429 when OpenAI lacks
  // the capacity. Priority and every other tier stay refused: they bill above the standard rates this meter reserves.
  if (!textInput || Object.keys(body).some(key => !allowed.has(key))
      || (body.service_tier !== undefined && body.service_tier !== 'default' && body.service_tier !== 'flex')) {
    return { error: 'Only inline text on the standard or flex service tier is priced by this gateway.', status: 400 };
  }
  const flex = body.service_tier === 'flex' ? price.flex ?? null : null;
  if (body.service_tier === 'flex' && !flex) {
    return { error: `No flex price is configured for model "${model}"; a flex call is refused.`, status: 403 };
  }
  // OpenAI takes at most four cache writes a request.
  if (!cacheHintsValid(body) || breakpoints > 4) {
    return { error: 'Prompt-cache hints must be a bounded key, a documented retention, a 30m ttl without prewarm and at most four explicit breakpoints.', status: 400 };
  }
  // The ceiling is the role's (Sept 26, 2026, Wave 5: the weekly post-mortem writes more than 16,000 tokens), else
  // 16,000; the reservation is sized from the max_output_tokens admitted under it.
  const ceiling = outputCeiling(env, role);
  const maxOutput = Number(body.max_output_tokens);
  if (!Number.isInteger(maxOutput) || maxOutput < 1 || maxOutput > ceiling) {
    return { error: `max_output_tokens is required, between 1 and ${ceiling}.`, status: 400 };
  }
  return { model, price, flex, maxOutput, ceiling };
}
