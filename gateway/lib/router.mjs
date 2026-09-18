// The gateway's routing table. Every request arrives here with a bearer token and nothing else;
// the venue credentials are added on the way out and never come back. The whole surface is:
//
//   GET|POST|DELETE /v1/kalshi/<path>     signed with the Kalshi key, forwarded to the venue
//   GET|POST|DELETE /v1/coinbase/<path>   signed with the Coinbase key, forwarded to the venue
//   GET             /v1/kalshi/ws-auth    handshake headers for the Kalshi WebSocket, 30 s of life
//   GET             /v1/coinbase/ws-jwt   a JWT for the Coinbase user WebSocket, 120 s of life
//   GET             /v1/health            caps, counters, kill switch, watchdog
//   POST            /v1/kill /v1/unkill   the kill switch, which lives outside the trading VM
//
// The two ws-* routes are the only ones that hand the VM credential material, and what they hand
// over is short-lived and read-only: neither venue accepts an order over its WebSocket. A POST to
// `/v1/kalshi/account/api_usage_level/upgrade` passes as an ordinary forwarded write; it creates
// no order, so the caps do not see it (`caps.createsOrder`).
//
// `gate` is the Durable Object stub (or, in tests, the gate itself): every method is awaited, so
// the same router works against both.

import { json, fail, authorized, readBody } from './http.mjs';
import { composeNotice, NOTICE_KINDS, FROM, TO } from './email.mjs';
import { createsOrder, notional, isCoinbaseFuture, REFERENCE_HEADER, allowedVenuePath } from './caps.mjs';
import * as kalshi from './kalshi.mjs';
import * as coinbase from './coinbase.mjs';

export const VENUES = ['kalshi', 'coinbase'];
//: A venue product listing (price, contract size) reused across orders for this long.
const PRODUCT_CACHE_MS = 60_000;
const productCache = new Map();
const METHODS = ['GET', 'POST', 'DELETE'];
const ALLOW = METHODS.join(', ');

/** The venue and venue path a gateway path names, or `null` when it names neither. */
export function parseRoute(pathname) {
  const match = /^\/v1\/(kalshi|coinbase)\/(.+)$/.exec(pathname);
  if (!match) return null;
  const path = match[2].replace(/^\/+/, '');
  // No traversal, no empty segments: a forwarded path is a venue path, not a filesystem one.
  if (!path || path.split('/').some(segment => segment === '' || segment === '.' || segment === '..')) return null;
  return { venue: match[1], path };
}

export async function route(request, env, { gate, fetcher = fetch, now = Date.now, nonce, mailer = null } = {}) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '') || '/';

  const ownerAction = path === '/v1/unkill';
  if (!authorized(request, ownerAction ? env.GATEWAY_ADMIN_TOKEN : env.GATEWAY_TOKEN)) {
    return fail('Unauthorized.', 401, { 'WWW-Authenticate': 'Bearer' });
  }

  if (path === '/v1/health') {
    if (request.method !== 'GET' && request.method !== 'HEAD') return fail('Method not allowed.', 405, { Allow: 'GET' });
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

  if (path === '/v1/kalshi/ws-auth' || path === '/v1/coinbase/ws-jwt') {
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    try {
      return json(await wsCredential(path, env, { now: now(), nonce }));
    } catch (error) {
      return fail(`Gateway credentials are unusable: ${error.message}`, 503);
    }
  }

  const target = parseRoute(path);
  if (!target) return fail('Not found.', 404);
  if (!METHODS.includes(request.method)) return fail('Method not allowed.', 405, { Allow: ALLOW });
  if (!allowedVenuePath(target.venue, request.method, target.path)) {
    return fail('Not a path this gateway signs.', 403);
  }

  const body = await readBody(request);
  if (body.error) return fail(body.error, 413);

  // --- caps, before anything is signed or sent -------------------------------------------------
  let reservation = null;
  if (createsOrder(target.venue, request.method, target.path)) {
    let parsed = null;
    try {
      parsed = body.text ? JSON.parse(body.text) : null;
    } catch {
      return fail('An order body must be JSON.', 400);
    }
    let reference = request.headers.get(REFERENCE_HEADER);
    let contractSize = null;
    if (target.venue === 'coinbase') {
      const leg = Object.values(parsed?.order_configuration || {}).find(v => v && typeof v === 'object');
      const product = String(parsed?.product_id || '');
      const future = isCoinbaseFuture(product);
      if ((leg?.base_size && !leg.quote_size && !leg.limit_price) || future) {
        // A market order has no enforceable limit. Its reference must come from the venue,
        // never from the trading VM that is asking us to authorize the spend. A futures order
        // also needs the venue's contract size, whatever the caller says its notional is.
        if (!/^[A-Z0-9-]{3,80}$/.test(product)) return fail('Invalid product id.', 400);
        // Sept 18, 2026: the venue rate-limited the Worker's bare product fetch (HTTP 429) and
        // a live order was refused for it. The lookup is signed like every other venue call,
        // and a product's listing is kept for PRODUCT_CACHE_MS across orders.
        const cacheMs = Number(env.PRODUCT_CACHE_MS ?? PRODUCT_CACHE_MS);
        let data = cacheMs > 0 ? productCache.get(product) : null;
        if (!data || data.expires < Date.now()) {
          let quote = null;
          try {
            const productPath = `api/v3/brokerage/market/products/${product}`;
            let headers = { 'User-Agent': 'ltcm-gateway/1.0', Accept: 'application/json' };
            try {
              const signed = await sign({ venue: 'coinbase', path: productPath }, new Request(`https://x/${productPath}`, { method: 'GET' }), env, { now: now(), nonce });
              headers = signed.headers;
            } catch { /* unsigned when the venue key is not configured */ }
            quote = await fetcher(`https://api.coinbase.com/${productPath}`, {
              method: 'GET', signal: AbortSignal.timeout(8000), redirect: 'follow', headers,
            });
          } catch (error) {
            return fail(`Cannot independently price this order: ${error?.name || 'fetch failed'}.`, 503);
          }
          if (!quote.ok) return fail(`Cannot independently price this order: venue HTTP ${quote.status}.`, 503);
          try {
            data = { ...(await quote.json()), expires: Date.now() + cacheMs };
          } catch { return fail('Cannot independently price this order: unreadable venue answer.', 503); }
          if (cacheMs > 0) productCache.set(product, data);
          if (productCache.size > 256) productCache.clear();
        }
        try {
          if (!(Number(data.price) > 0)) return fail('Cannot independently price this order: no venue price.', 503);
          if (!leg?.limit_price) reference = String(Number(data.price) * 1.10);
          if (future) {
            contractSize = String(data?.future_product_details?.contract_size ?? '');
            if (!(Number(contractSize) > 0)) return fail('Cannot price this futures order: the venue lists no contract size.', 503);
          }
        } catch { return fail('Cannot independently price this order: unreadable venue answer.', 503); }
      }
    }
    const priced = notional(target.venue, parsed, { reference, contractSize });
    if (priced.error) return fail(priced.error, 400);
    const decision = await gate.reserve({ micro: String(priced.micro) });
    if (!decision.ok) return json({ error: decision.error, ...(decision.cap ? { cap: decision.cap } : {}) }, decision.status);
    reservation = decision;
  }

  // --- sign and forward ------------------------------------------------------------------------
  let outbound;
  try {
    outbound = await sign(target, request, env, { now: now(), nonce });
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

/** Short-lived WebSocket credential material for the VM: handshake headers, or a socket JWT. */
async function wsCredential(path, env, { now, nonce }) {
  if (path === '/v1/kalshi/ws-auth') {
    if (!env.KALSHI_KEY_ID || !env.KALSHI_PRIVATE_KEY) throw new Error('kalshi not configured');
    const headers = await kalshi.wsAuthHeaders({ keyId: env.KALSHI_KEY_ID, privateKeyPem: env.KALSHI_PRIVATE_KEY, now });
    return { headers, path: kalshi.WS_PATH, expires_in: kalshi.WS_AUTH_TTL_SECONDS };
  }
  if (!env.COINBASE_KEY_NAME || !env.COINBASE_API_SECRET) throw new Error('coinbase not configured');
  const jwt = await coinbase.mintWsJwt({
    keyName: env.COINBASE_KEY_NAME, secret: env.COINBASE_API_SECRET, now, ...(nonce ? { nonce } : {}),
  });
  return { jwt, expires_in: coinbase.LIFETIME_SECONDS };
}

async function sign({ venue, path }, request, env, { now, nonce }) {
  const search = new URL(request.url).search;
  const headers = {
    Accept: 'application/json',
    ...(request.method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
    'User-Agent': 'ltcm-gateway/1.0',
  };
  if (venue === 'kalshi') {
    if (!env.KALSHI_KEY_ID || !env.KALSHI_PRIVATE_KEY) throw new Error('not configured');
    Object.assign(headers, await kalshi.authHeaders({
      keyId: env.KALSHI_KEY_ID, privateKeyPem: env.KALSHI_PRIVATE_KEY, method: request.method, path, now,
    }));
    return { url: kalshi.target(path, search), headers };
  }
  if (!env.COINBASE_KEY_NAME || !env.COINBASE_API_SECRET) throw new Error('not configured');
  const token = await coinbase.mintJwt({
    keyName: env.COINBASE_KEY_NAME, secret: env.COINBASE_API_SECRET, method: request.method, path, now,
    ...(nonce ? { nonce } : {}),
  });
  return { url: coinbase.target(path, search), headers: { ...headers, Authorization: `Bearer ${token}` } };
}
