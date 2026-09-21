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
      if (/^[A-Za-z0-9._:-]{1,80}$/.test(model) && [input, cached, output, longInput, longCached, longOutput].every(Number.isFinite)
          && input > 0 && cached >= 0 && cached <= input && output > 0
          && longInput >= input && longCached >= cached && longCached <= longInput && longOutput >= output) {
        out[model] = { input, cached, output, long_input: longInput, long_cached: longCached, long_output: longOutput };
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
  const long = input > 272000;
  return micro(((input - cached) * (long ? price.long_input ?? price.input : price.input)
    + cached * (long ? price.long_cached ?? price.cached : price.cached)
    + output * (long ? price.long_output ?? price.output : price.output)) / 1e6);
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
  const allowed = new Set(['model', 'input', 'max_output_tokens', 'reasoning', 'stream', 'background', 'service_tier']);
  const textInput = typeof body.input === 'string' || (Array.isArray(body.input) && body.input.every(item =>
    item && typeof item === 'object' && ['system', 'developer', 'user', 'assistant'].includes(item.role)
    && typeof item.content === 'string' && Object.keys(item).every(key => ['role', 'content'].includes(key))));
  if (!textInput || Object.keys(body).some(key => !allowed.has(key))
      || (body.service_tier !== undefined && body.service_tier !== 'default')) {
    return { error: 'Only inline text on the standard service tier is priced by this gateway.', status: 400 };
  }
  const maxOutput = Number(body.max_output_tokens);
  if (!Number.isInteger(maxOutput) || maxOutput < 1 || maxOutput > MAX_OUTPUT_TOKENS) {
    return { error: `max_output_tokens is required, between 1 and ${MAX_OUTPUT_TOKENS}.`, status: 400 };
  }
  return { model, price, maxOutput };
}
