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
//: The most output one call may ask for. The reservation is sized from it.
export const MAX_OUTPUT_TOKENS = 16000;

/** `{ model: { input, cached, output } }` in dollars per million tokens, from `FRONTIER_MODELS`. */
export function priceTable(env = {}) {
  try {
    const table = JSON.parse(env.FRONTIER_MODELS || '{}');
    const out = {};
    for (const [model, row] of Object.entries(table)) {
      const input = Number(row?.input), cached = Number(row?.cached ?? row?.input), output = Number(row?.output);
      const longInput = Number(row?.long_input ?? input), longCached = Number(row?.long_cached ?? cached);
      const longOutput = Number(row?.long_output ?? output);
      // `input` is the cache-write rate, the dearest an input token can be. `uncached` is the
      // plain rate for a token neither read from nor written to the cache; absent, it is `input`,
      // so a table without it prices exactly as before.
      const uncached = Number(row?.uncached ?? input), longUncached = Number(row?.long_uncached ?? longInput);
      if (/^[A-Za-z0-9._:-]{1,80}$/.test(model) && [input, cached, output, longInput, longCached, longOutput, uncached, longUncached].every(Number.isFinite)
          && input > 0 && cached >= 0 && cached <= input && output > 0
          && longInput >= input && longCached >= cached && longCached <= longInput && longOutput >= output
          && uncached >= cached && uncached <= input && longUncached >= longCached && longUncached <= longInput && longUncached >= uncached) {
        out[model] = { input, cached, output, long_input: longInput, long_cached: longCached, long_output: longOutput,
          uncached, long_uncached: longUncached };
      }
    }
    return out;
  } catch {
    return {};
  }
}

export const monthCapMicro = env => parseUsdMicro(env.FRONTIER_MONTH_USD, 0n);

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
 * Check a request body before it is sent. `{ model, price, maxOutput }` or `{ error, status }`.
 * Streaming and background calls are refused: the usage block that settles the bill arrives
 * with a complete response, and a call that outlives the request cannot be settled at all.
 */
export function admit(body, env) {
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
  if (!textInput || Object.keys(body).some(key => !allowed.has(key))
      || (body.service_tier !== undefined && body.service_tier !== 'default')) {
    return { error: 'Only inline text on the standard service tier is priced by this gateway.', status: 400 };
  }
  // OpenAI takes at most four cache writes a request.
  if (!cacheHintsValid(body) || breakpoints > 4) {
    return { error: 'Prompt-cache hints must be a bounded key, a documented retention, a 30m ttl without prewarm and at most four explicit breakpoints.', status: 400 };
  }
  const maxOutput = Number(body.max_output_tokens);
  if (!Number.isInteger(maxOutput) || maxOutput < 1 || maxOutput > MAX_OUTPUT_TOKENS) {
    return { error: `max_output_tokens is required, between 1 and ${MAX_OUTPUT_TOKENS}.`, status: 400 };
  }
  return { model, price, maxOutput };
}
