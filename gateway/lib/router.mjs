// The gateway's routing table. Every request arrives here with a bearer token and nothing else;
// the venue credentials are added on the way out and never come back. The whole surface is:
//
//   GET             /v1/health               caps, counters, kill switch, frontier month, pulls, watchdog
//   POST            /v1/kill                 engage the kill switch: the runtime token may
//   POST            /v1/unkill               release it: GATEWAY_ADMIN_TOKEN only, the owner's
//   GET|POST|DELETE /v1/kalshi/<path>        signed with the Kalshi key, forwarded to the venue
//   GET|POST|DELETE /v1/alpaca/<path>        keyed with the Alpaca headers, forwarded to the venue
//   GET|POST|DELETE /v1/alpaca-paper/<path>  the paper account: same paths, simulated money, no caps
//   GET             /v1/kalshi/ws-auth       handshake headers for the Kalshi WebSocket, 30 s of life
//   POST            /v1/notify               one trade notice mailed to the owner, capped per day
//   GET             /v1/frontier/models      the model ids the OpenAI key can reach, and which are priced
//   POST            /v1/frontier/responses   one frontier call, reserved and settled against the month
//   POST            /v1/typesafe/systemone  funded Jev judgments, with durable request identities
//   POST            /v1/github/pr            a proposal becomes a branch and a pull request, never a push
//   GET             /v1/github/pr/<n>        that pull request and its CI, so the VM can watch it
//   GET             /v1/github/pr/<n>/failures  why CI refused it: failed runs and their annotations
//
// Anything else is a 404, and so is any venue name but these three (Coinbase was removed on
// Sept 19, 2026). A venue path outside `caps.VENUE_PATHS` is a 403 before any key is touched.
//
// The ws-auth route is the only one that hands the VM credential material, and what it hands
// over is short-lived and read-only: Kalshi accepts no order over its WebSocket. A POST to
// `/v1/kalshi/account/api_usage_level/upgrade` passes as an ordinary forwarded write; it creates
// no order, so the caps do not see it (`caps.createsOrder`).
//
// The kill switch is checked where an order is reserved, so it stops every order-creating call
// on a real venue and nothing else: reads and cancels pass, and the paper venue never reaches
// the gate at all.
//
// The GitHub routes move no money, so the kill switch does not stop them: a halted floor may still
// propose its own repair. There is deliberately no merge route. CI judges a pull request and a
// repository workflow merges it; the most this gateway can do to `main` is ask.
//
// `gate` is the Durable Object stub (or, in tests, the gate itself): every method is awaited, so
// the same router works against both.

import { json, fail, authorized, readBody } from './http.mjs';
import { composeNotice, NOTICE_KINDS, FROM, TO } from './email.mjs';
import { createsOrder, notional, REFERENCE_HEADER, PURPOSE_HEADER, allowedVenuePath, isOptionSymbol } from './caps.mjs';
import * as kalshi from './kalshi.mjs';
import * as alpaca from './alpaca.mjs';
import * as frontier from './frontier.mjs';
import * as equity from './equity.mjs';
import * as typesafe from './typesafe.mjs';
import * as github from './github.mjs';

export const VENUES = ['kalshi', 'alpaca', 'alpaca-paper'];
//: Venues that hold no real money. Their orders are never metered and the kill switch does not
//: stop them: the paper league must keep learning while real trading is halted.
export const PAPER_VENUES = ['alpaca-paper'];
//: The venue whose path rules a venue shares.
const rulesOf = venue => (venue === 'alpaca-paper' ? 'alpaca' : venue);
//: A venue quote reused across orders for this long.
const PRODUCT_CACHE_MS = 60_000;
const productCache = new Map();
const METHODS = ['GET', 'POST', 'DELETE'];
const ALLOW = METHODS.join(', ');

/** The venue and venue path a gateway path names, or `null` when it names neither. */
export function parseRoute(pathname) {
  const match = /^\/v1\/(kalshi|alpaca-paper|alpaca)\/(.+)$/.exec(pathname);
  if (!match) return null;
  const path = match[2].replace(/^\/+/, '');
  // No traversal, no empty segments: a forwarded path is a venue path, not a filesystem one.
  if (!path || path.split('/').some(segment => segment === '' || segment === '.' || segment === '..')) return null;
  return { venue: match[1], path };
}

export async function route(request, env, { gate, fetcher = fetch, now = Date.now, mailer = null } = {}) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '') || '/';

  const ownerAction = path === '/v1/unkill';
  if (!authorized(request, ownerAction ? env.GATEWAY_ADMIN_TOKEN : env.GATEWAY_TOKEN)) {
    return fail('Unauthorized.', 401, { 'WWW-Authenticate': 'Bearer' });
  }

  if (path === '/v1/health') {
    if (request.method !== 'GET' && request.method !== 'HEAD') return fail('Method not allowed.', 405, { Allow: 'GET' });
    // The health read reports the stored equity reading and never refreshes it: the House reads its
    // kill switch here on the order path and treats a slow answer as the switch engaged, and a
    // refresh reads both venues one after the other. The frontier path refreshes it (ten minutes).
    return json(await gate.status());
  }
  if (path === '/v1/kill' || path === '/v1/unkill') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    await gate.setKill(path === '/v1/kill');
    return json(await gate.status());
  }

  if (path === '/v1/notify') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    const body = await readBody(request, 32 * 1024);
    if (body.error) return fail(body.error, 413);
    let facts;
    try {
      facts = JSON.parse(body.text || '');
    } catch {
      return fail('The notice must be a JSON object.', 400);
    }
    if (!facts || typeof facts !== 'object' || Array.isArray(facts) || !NOTICE_KINDS.includes(facts.kind)) {
      return fail('The notice needs a known kind.', 400);
    }
    const message = composeNotice(facts);
    if (!message) return fail('The notice could not be composed.', 400);
    const cap = Number(env.NOTIFY_MAX_PER_DAY || 40);
    const noticeId = typeof facts.notice_id === 'string' && /^[a-zA-Z0-9:_-]{1,160}$/.test(facts.notice_id) ? facts.notice_id : null;
    if (noticeId && await gate.noticeDelivered(noticeId, now())) return json({ sent: true, duplicate: true });
    if (await gate.noticesToday(now()) >= cap) return fail('The day\'s notice cap is reached.', 429, { 'Retry-After': '3600' });
    if (!mailer) return json({ sent: false, reason: 'no mail binding', subject: message.subject });
    try {
      await mailer({ from: env.ALERT_FROM || FROM, to: env.ALERT_TO || TO, ...message, at: now() });
    } catch (error) {
      return fail(`The mail could not be sent: ${error?.name || 'send_failed'}.`, 502);
    }
    const count = await gate.recordNotice(now(), noticeId);
    return json({ sent: true, subject: message.subject, notices_today: count });
  }

  if (path === '/v1/kalshi/ws-auth') {
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    try {
      return json(await wsCredential(path, env, { now: now() }));
    } catch (error) {
      return fail(`Gateway credentials are unusable: ${error.message}`, 503);
    }
  }

  if (path === '/v1/frontier/models') {
    // Free and read-only: which models the key can reach, so a price is never set on a guess.
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    if (!env.OPENAI_SECRET_KEY) return fail('The frontier model is not configured.', 503);
    try {
      const upstream = await fetcher(frontier.HOST + '/v1/models', {
        method: 'GET', headers: { Accept: 'application/json', Authorization: `Bearer ${env.OPENAI_SECRET_KEY}` },
        redirect: 'manual', signal: AbortSignal.timeout(20000),
      });
      const data = await upstream.json().catch(() => null);
      if (!upstream.ok) return fail(`The provider answered HTTP ${upstream.status}.`, 502);
      return json({ models: (data?.data || []).map(row => row?.id).filter(id => typeof id === 'string').sort(), priced: Object.keys(frontier.priceTable(env)) });
    } catch {
      return fail('The frontier provider did not answer.', 502);
    }
  }
  if (path === '/v1/frontier/responses') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return frontierCall(request, env, { gate, fetcher, now });
  }

  if (path === '/v1/typesafe/systemone') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return typesafeCall(request, env, { gate, fetcher, now });
  }

  if (path === '/v1/github/pr') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return proposePull(request, env, { gate, fetcher, now });
  }
  const refusals = /^\/v1\/github\/pr\/([1-9][0-9]{0,8})\/failures$/.exec(path);
  if (refusals) {
    // Read-only and free: why CI refused, so a proposal can be revised against the real reason.
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    const account = github.configured(env);
    if (!account) return fail('GitHub is not configured.', 503);
    const found = await github.pullFailures({ ...account, number: Number(refusals[1]), fetcher });
    return found.error ? fail(found.error, found.status) : json(found);
  }
  const watched = /^\/v1\/github\/pr\/([1-9][0-9]{0,8})$/.exec(path);
  if (watched) {
    // Read-only and free: the VM holds no GitHub credential, so this is how it learns CI's verdict.
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    const account = github.configured(env);
    if (!account) return fail('GitHub is not configured.', 503);
    const status = await github.pullStatus({ ...account, number: Number(watched[1]), fetcher });
    return status.error ? fail(status.error, status.status) : json(status);
  }

  const target = parseRoute(path);
  if (!target) return fail('Not found.', 404);
  if (!METHODS.includes(request.method)) return fail('Method not allowed.', 405, { Allow: ALLOW });
  if (!allowedVenuePath(rulesOf(target.venue), request.method, target.path)) {
    return fail('Not a path this gateway signs.', 403);
  }

  const body = await readBody(request);
  if (body.error) return fail(body.error, 413);

  // --- caps, before anything is signed or sent -------------------------------------------------
  let reservation = null;
  if (!PAPER_VENUES.includes(target.venue) && createsOrder(target.venue, request.method, target.path)) {
    let parsed = null;
    try {
      parsed = body.text ? JSON.parse(body.text) : null;
    } catch {
      return fail('An order body must be JSON.', 400);
    }
    let reference = request.headers.get(REFERENCE_HEADER);
    if (target.venue === 'alpaca' && !isOptionSymbol(parsed?.symbol) && !parsed?.notional && !parsed?.limit_price && !parsed?.stop_price) {
      // A market order has no enforceable limit, so its reference comes from the venue's own
      // quote, signed like every other call. An unpriceable order is refused, never passed.
      const symbol = String(parsed?.symbol || '');
      if (!/^[A-Za-z0-9.\/-]{1,24}$/.test(symbol)) return fail('Invalid symbol.', 400);
      const crypto = symbol.includes('/');
      const quotePath = crypto
        ? `v1beta3/crypto/us/latest/quotes?symbols=${encodeURIComponent(symbol)}`
        : `v2/stocks/${encodeURIComponent(symbol)}/quotes/latest`;
      const cacheKey = `alpaca:${symbol}`;
      const cacheMs = Number(env.PRODUCT_CACHE_MS ?? PRODUCT_CACHE_MS);
      let data = cacheMs > 0 ? productCache.get(cacheKey) : null;
      if (!data || data.expires < Date.now()) {
        let quote = null;
        try {
          const [bare, query = ''] = quotePath.split('?');
          const signed = await sign({ venue: 'alpaca', path: bare }, new Request(`https://x/${bare}${query ? '?' + query : ''}`, { method: 'GET' }), env, { now: now() });
          quote = await fetcher(signed.url, { method: 'GET', headers: signed.headers, signal: AbortSignal.timeout(8000), redirect: 'follow' });
        } catch (error) {
          return fail(`Cannot independently price this order: ${error?.name || 'fetch failed'}.`, 503);
        }
        if (!quote.ok) return fail(`Cannot independently price this order: venue HTTP ${quote.status}.`, 503);
        try {
          data = { ...(await quote.json()), expires: Date.now() + cacheMs };
        } catch { return fail('Cannot independently price this order: unreadable venue answer.', 503); }
        if (cacheMs > 0) productCache.set(cacheKey, data);
        if (productCache.size > 256) productCache.clear();
      }
      // A stock answer is `quote` beside `symbol`; a crypto answer is `quotes`, keyed by symbol.
      const level = data.quote || data.quotes?.[symbol] || null;
      const ask = Number(level?.ap ?? level?.AskPrice ?? 0);
      const bid = Number(level?.bp ?? level?.BidPrice ?? 0);
      const price = ask > 0 ? ask : bid;
      if (!(price > 0)) return fail('Cannot independently price this order: no venue quote.', 503);
      reference = String(price * 1.10);  // a market order may fill through the touch
    }
    const exit = String(request.headers.get(PURPOSE_HEADER) || '').toLowerCase() === 'exit';
    const priced = notional(target.venue, parsed, { reference, exit });
    if (priced.error) return fail(priced.error, 400);
    const decision = await gate.reserve({ micro: String(priced.micro), exit, venue: target.venue });
    if (!decision.ok) return json({ error: decision.error, ...(decision.cap ? { cap: decision.cap } : {}) }, decision.status);
    reservation = decision;
  }

  // --- sign and forward ------------------------------------------------------------------------
  let outbound;
  try {
    outbound = await sign(target, request, env, { now: now() });
  } catch (error) {
    if (reservation) await gate.refund(reservation);
    return fail(`Gateway credentials for ${target.venue} are unusable: ${error.message}`, 503);
  }

  try {
    const upstream = await fetcher(outbound.url, {
      method: request.method,
      headers: outbound.headers,
      body: body.text ?? undefined,
      redirect: 'manual',
      signal: AbortSignal.timeout(30000),
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') || 'application/json; charset=utf-8',
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store',
      },
    });
  } catch (error) {
    // A timeout can occur after acceptance. Keep the reservation: absence of a response is
    // not proof of absence of an order. Only failures before dispatch may refund it.
    return fail(`The ${target.venue} API did not answer.`, 502);
  }
}

/** Short-lived WebSocket credential material for the VM: the Kalshi handshake headers. */
async function wsCredential(path, env, { now }) {
  if (path !== '/v1/kalshi/ws-auth') throw new Error('unknown credential route');
  if (!env.KALSHI_KEY_ID || !env.KALSHI_PRIVATE_KEY) throw new Error('kalshi not configured');
  const headers = await kalshi.wsAuthHeaders({ keyId: env.KALSHI_KEY_ID, privateKeyPem: env.KALSHI_PRIVATE_KEY, now });
  return { headers, path: kalshi.WS_PATH, expires_in: kalshi.WS_AUTH_TTL_SECONDS };
}

async function sign({ venue, path }, request, env, { now }) {
  const search = new URL(request.url).search;
  const headers = {
    Accept: 'application/json',
    ...(request.method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
    'User-Agent': 'ltcm-gateway/1.0',
  };
  if (venue === 'alpaca-paper') {
    if (!env.ALPACA_PAPER_KEY_ID || !env.ALPACA_PAPER_SECRET_KEY) throw new Error('not configured');
    Object.assign(headers, alpaca.authHeaders({ keyId: env.ALPACA_PAPER_KEY_ID, secretKey: env.ALPACA_PAPER_SECRET_KEY }));
    return { url: alpaca.target(path, search, { paper: true }), headers };
  }
  if (venue === 'alpaca') {
    if (!env.ALPACA_KEY_ID || !env.ALPACA_SECRET_KEY) throw new Error('not configured');
    Object.assign(headers, alpaca.authHeaders({ keyId: env.ALPACA_KEY_ID, secretKey: env.ALPACA_SECRET_KEY }));
    return { url: alpaca.target(path, search), headers };
  }
  if (venue === 'kalshi') {
    if (!env.KALSHI_KEY_ID || !env.KALSHI_PRIVATE_KEY) throw new Error('not configured');
    Object.assign(headers, await kalshi.authHeaders({
      keyId: env.KALSHI_KEY_ID, privateKeyPem: env.KALSHI_PRIVATE_KEY, method: request.method, path, now,
    }));
    return { url: kalshi.target(path, search), headers };
  }
  throw new Error(`unknown venue ${String(venue)}`);
}

/** One funded semantic request. Ambiguous responses retain their reservation and identity. */
async function typesafeCall(request, env, { gate, fetcher, now }) {
  if (!env.TYPE_SAFE_TOKEN) return fail('TypeSafe is not configured.', 503);
  const body = await readBody(request, typesafe.MAX_BODY_BYTES);
  if (body.error) return fail(body.error, 413);
  let parsed;
  try { parsed = JSON.parse(body.text || ''); } catch { return fail('The request must be JSON.', 400); }
  const error = typesafe.admit(parsed);
  if (error) return fail(error, 400);
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body.text)))]
    .map(b => b.toString(16).padStart(2, '0')).join('');
  const hold = await gate.typesafeReserve({ id: request.headers.get('X-LTCM-Request'), digest, at: now() });
  if (!hold.ok) return json({ error: hold.error, ...(hold.cap ? { cap: hold.cap } : {}) }, hold.status);
  let upstream, data;
  try {
    upstream = await fetcher(typesafe.ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json',
        Authorization: `Bearer ${env.TYPE_SAFE_TOKEN}`, 'User-Agent': 'ltcm-gateway/1.0' },
      body: body.text, redirect: 'manual', signal: AbortSignal.timeout(30000),
    });
    const response = await readBody(upstream, 128 * 1024);
    if (response.error) throw new Error('oversize response');
    data = JSON.parse(response.text);
  } catch {
    await gate.typesafeSettle({ id: hold.id, actual: null });
    return fail('TypeSafe did not return a complete JSON response; the reservation is retained.', 502);
  }
  const cost = typesafe.actualCost(data?.usage);
  const settled = await gate.typesafeSettle({ id: hold.id, actual: cost === null ? null : String(cost) });
  const headers = { 'X-LTCM-Cost-USD': settled.cost_usd, 'X-LTCM-Cost-Known': String(settled.cost_known) };
  // Never echo provider error text: it can contain request data or authentication diagnostics.
  if (!upstream.ok) return json({ error: `TypeSafe returned HTTP ${upstream.status}; no automatic retry.` }, 502, headers);
  if (!typesafe.validAnswers(parsed, data)) return json({ error: 'TypeSafe returned incompatible typed answers.' }, 502, headers);
  return json(data, 200, headers);
}

/** One frontier call, reserved at a conservative ceiling and settled from reported usage. */
async function frontierCall(request, env, { gate, fetcher, now }) {
  if (!env.OPENAI_SECRET_KEY) return fail('The frontier model is not configured.', 503);
  const body = await readBody(request, 512 * 1024);
  if (body.error) return fail(body.error, 413);
  let parsed;
  try {
    parsed = JSON.parse(body.text || '');
  } catch {
    return fail('The request must be JSON.', 400);
  }
  const admitted = frontier.admit(parsed, env);
  if (admitted.error) return fail(admitted.error, admitted.status);
  const bytes = new TextEncoder().encode(body.text).length;
  await equity.refresh(env, gate, { fetcher, now });  // profit-indexed cap: the accounts read at most every ten minutes
  const hold = await gate.frontierReserve({ micro: String(frontier.worstCase(admitted.price, bytes, admitted.maxOutput)), at: now() });
  if (!hold.ok) return json({ error: hold.error, ...(hold.cap ? { cap: hold.cap } : {}) }, hold.status);
  const agent = request.headers.get(frontier.AGENT_HEADER);
  let upstream;
  try {
    upstream = await fetcher(frontier.HOST + frontier.PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', Authorization: `Bearer ${env.OPENAI_SECRET_KEY}`, 'User-Agent': 'ltcm-gateway/1.0' },
      body: body.text,
      redirect: 'manual',
      // Just under the House's own 600-second read. At 280 seconds a high-effort consultation
      // was cut off before it answered and still kept its whole worst case on the month: on
      // Sept 21, 2026 most agent consultations ended this way, about $3 each for nothing.
      signal: AbortSignal.timeout(570000),
    });
  } catch {
    // Nothing came back. The provider may still bill a call it received, so the hold stays.
    await gate.frontierSettle({ month: hold.month, reserved: hold.micro, actual: null, agent, at: now() });
    return fail('The frontier model did not answer.', 502);
  }
  const text = await upstream.text();
  let actual = null;
  if (upstream.ok) {
    try { actual = frontier.actualCost(admitted.price, JSON.parse(text).usage); } catch { actual = null; }
  } else if (upstream.status >= 400 && upstream.status < 500) {
    actual = 0n;  // refused by the provider before any generation: nothing was billed
  }
  const settled = await gate.frontierSettle({ month: hold.month, reserved: hold.micro, actual: actual === null ? null : String(actual), agent, at: now() });
  return new Response(text, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'application/json; charset=utf-8',
      'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
      ...(settled?.cost_usd ? { 'X-LTCM-Cost-USD': settled.cost_usd } : {}),
    },
  });
}

/**
 * One proposal from the frontier model, opened as a pull request. The proposal is checked against
 * its role's paths before GitHub hears of it, and takes one of the day's places before the first
 * call; the place is given back when the attempt made no new branch, so a retry of a proposal
 * that is already open costs nothing and a GitHub outage does not spend the day.
 */
async function proposePull(request, env, { gate, fetcher, now }) {
  const account = github.configured(env);
  if (!account) return fail('GitHub is not configured.', 503);
  const body = await readBody(request, github.MAX_REQUEST_BYTES);
  if (body.error) return fail(body.error, 413);
  let parsed;
  try {
    parsed = JSON.parse(body.text || '');
  } catch {
    return fail('The proposal must be JSON.', 400);
  }
  const proposal = github.admit(parsed);
  if (proposal.error) return json({ error: proposal.error, ...(proposal.path !== undefined ? { path: proposal.path } : {}) }, proposal.status);
  const hold = await gate.pullReserve({ at: now() });
  if (!hold.ok) return json({ error: hold.error, cap: hold.cap }, hold.status, { 'Retry-After': '3600' });
  const result = await github.openPullRequest({ ...account, proposal, fetcher });
  if (!result.created) await gate.pullRefund({ day: hold.day, at: now() });
  if (result.error) return fail(result.error, result.status);
  return json({ ok: true, branch: result.branch, number: result.number, url: result.url, head: result.head });
}
