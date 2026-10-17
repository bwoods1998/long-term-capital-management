// The Tiingo daily route (release R1, the deep key; the history-expansion plan's D1): `GET /v1/tiingo/daily/<SYM>/prices`.
//
// Read-only and $0. The owner's Tiingo token (Starter: internal use only) is a gateway secret, `TIINGO_TOKEN`
// (`wrangler secret put TIINGO_TOKEN`): it is added on the way out and never returned, logged or echoed. The House's
// `equity_deep` job (league/ops/equity_deep.py) is the one caller: it fetches the sealed 2001-08 era itself, so no
// copy of it ever touches the desktop.
//
// THE ALLOWLIST. Only the 16 ETFs of the House universe with a pre-2016 history (`SYMBOLS`), and only days inside
// 1999-01-04..2019-12-31 (`FIRST_DAY`, `LAST_DAY`): the deep store's look-back, DVAL and TRAIN-D, and the 2016-19 SIP
// overlap its audit reads. Never a day of 2020 on: the reserve (2020-21), Validation (2025), the holdout and the
// forward days are sealed from this route whatever the House asks. A request outside it is a 403 before the token is
// touched.
//
// WHAT IS ANSWERED. `{symbol, start, end, rows}`, each row `{date, open, high, low, close, volume, divCash,
// splitFactor, factorStep}`: the raw bars as printed that day and the day's events. The vendor's adjusted columns are
// DROPPED here: an adjusted series is adjusted as of the fetch day, so its level before 2016 carries every later
// distribution (2025-2026 among them). In their place `factorStep` says whether the vendor's own adjustment factor
// (adjClose / close) moved from the row before by more than `STEP_TOLERANCE`, which is all the House's audit needs
// ("every factor step reconciles to a listed event"). A row of another day than asked, or a figure that is not a
// number, refuses the whole answer (502).
//
// Tiingo Starter allows 50 requests an hour and 1,000 a day; the House paces itself (one request every 75 s) and this
// route keeps no counter. It moves no money, so the kill switch does not stop it.

import { fail, json } from './http.mjs';

export const PREFIX = '/v1/tiingo/';
export const HOST = 'https://api.tiingo.com';
export const SYMBOLS = Object.freeze(['SPY', 'QQQ', 'IWM', 'DIA', 'XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU',
  'XLV', 'XLY', 'TLT', 'GLD']);
export const FIRST_DAY = '1999-01-04';
export const LAST_DAY = '2019-12-31';
export const KEPT = Object.freeze(['date', 'open', 'high', 'low', 'close', 'volume', 'divCash', 'splitFactor']);
export const STEP_TOLERANCE = 1e-6;
const ROUTE = /^\/v1\/tiingo\/daily\/([A-Za-z]{1,6})\/prices$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export const isTiingoPath = path => typeof path === 'string' && path.startsWith(PREFIX);

/** A real calendar day written as YYYY-MM-DD. */
export function validDay(text) {
  if (typeof text !== 'string' || !DAY.test(text)) return false;
  const day = new Date(`${text}T00:00:00Z`);
  return !Number.isNaN(day.getTime()) && day.toISOString().slice(0, 10) === text;
}

/** Why a request may not be forwarded (null: it may): the symbol, then the window. */
export function refusal(symbol, start, end) {
  if (!SYMBOLS.includes(String(symbol || '').toUpperCase())) return 'symbol';
  if (!validDay(start) || !validDay(end) || start > end) return 'window';
  if (start < FIRST_DAY || end > LAST_DAY) return 'window';
  return null;
}

/** The answer rows, kept columns and `factorStep` only; {error} for a row this route will not pass along. */
export function shape(rows, start, end) {
  if (!Array.isArray(rows)) return { error: 'Tiingo answered something other than a list of bars.' };
  const out = [];
  let previous = null;
  for (const row of rows) {
    if (!row || typeof row !== 'object') return { error: 'Tiingo answered a bar that is not an object.' };
    const date = String(row.date ?? '').slice(0, 10);
    if (!validDay(date) || date < start || date > end) return { error: 'Tiingo answered a day outside the request.' };
    const kept = { date };
    for (const name of KEPT.slice(1)) {
      const value = row[name];
      if (typeof value !== 'number' || !Number.isFinite(value)) return { error: `Tiingo's ${name} of ${date} is not a number.` };
      kept[name] = value;
    }
    const ratio = typeof row.adjClose === 'number' && Number.isFinite(row.adjClose) && row.close > 0 ? row.adjClose / row.close : null;
    kept.factorStep = previous !== null && ratio !== null && Math.abs(previous / ratio - 1) > STEP_TOLERANCE;
    previous = ratio;
    if (out.length && date <= out[out.length - 1].date) return { error: 'Tiingo answered days out of order.' };
    out.push(kept);
  }
  return { rows: out };
}

export async function tiingoRoute(request, env, { fetcher = fetch } = {}) {
  if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '');
  const match = ROUTE.exec(path);
  if (!match) return fail('Not found.', 404);
  const symbol = match[1].toUpperCase();
  const start = url.searchParams.get('startDate');
  const end = url.searchParams.get('endDate');
  const why = refusal(symbol, start, end);
  if (why === 'symbol') return json({ error: 'Only the 16 ETFs of the deep store are served.', cap: 'symbol' }, 403);
  if (why === 'window') {
    return json({ error: `Only days inside ${FIRST_DAY}..${LAST_DAY} are served, as startDate <= endDate.`, cap: 'window' }, 403);
  }
  const token = typeof env.TIINGO_TOKEN === 'string' ? env.TIINGO_TOKEN.trim() : '';
  if (token.length < 20) return json({ error: 'The Tiingo route is not configured (the owner step D1).', cap: 'setup' }, 503);
  const query = new URLSearchParams({ startDate: start, endDate: end, resampleFreq: 'daily', format: 'json' });
  let upstream;
  try {
    upstream = await fetcher(`${HOST}/tiingo/daily/${symbol.toLowerCase()}/prices?${query}`, {
      method: 'GET', headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
      redirect: 'manual', signal: AbortSignal.timeout(60000),
    });
  } catch {
    return fail('Tiingo did not answer.', 502);
  }
  if (!upstream.ok) return fail(`Tiingo answered HTTP ${upstream.status}.`, 502);
  const data = await upstream.json().catch(() => null);
  const shaped = shape(data, start, end);
  if (shaped.error) return fail(shaped.error, 502);
  return json({ symbol, start, end, rows: shaped.rows });
}
