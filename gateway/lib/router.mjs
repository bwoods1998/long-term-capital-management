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
import { createsOrder, notional, REFERENCE_HEADER } from './caps.mjs';
import * as kalshi from './kalshi.mjs';
import * as coinbase from './coinbase.mjs';

export const VENUES = ['kalshi', 'coinbase'];
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

export async function route(request, env, { gate, fetcher = fetch, now = Date.now, nonce } = {}) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '') || '/';

  if (!authorized(request, env.GATEWAY_TOKEN)) {
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
    const priced = notional(target.venue, parsed, { reference: request.headers.get(REFERENCE_HEADER) });
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
    // Nothing reached the venue, so no order exists and the reservation goes back. A venue that
    // answered at all keeps its reservation, however it answered.
    if (reservation) await gate.refund(reservation);
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
