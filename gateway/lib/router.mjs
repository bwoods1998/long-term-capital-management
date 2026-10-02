// The gateway's routing table. Every request arrives here with a bearer token and nothing else;
// the venue credentials are added on the way out and never come back. The whole surface is:
//
//   GET             /v1/health               caps, counters, the caps by maximum loss, kill switch, frontier month, pulls, watchdog
//   POST            /v1/kill                 engage the kill switch: the runtime token may, and so may the owner's
//   POST            /v1/unkill               release it: GATEWAY_ADMIN_TOKEN only, the owner's
//                                            (both written to the admin log, with every admin-token call: V3-A)
//   GET|POST|DELETE /v1/kalshi/<path>        signed with the Kalshi key, forwarded to the venue
//   GET|POST|DELETE /v1/alpaca/<path>        keyed with the Alpaca headers, forwarded to the venue; its orders are
//                                            options capped by maximum loss against the account's own equity, and
//                                            stock only to close shares it holds (`realOrder`, Sept 26, 2026)
//   GET|POST|DELETE /v1/alpaca-paper/<path>  the practice account: same paths, simulated money, no caps;
//                                            its option orders are held to defined-risk shapes
//   GET             /v1/kalshi/ws-auth       handshake headers for the Kalshi WebSocket, 30 s of life
//   POST            /v1/notify               one notice mailed to the owner (a trade, a stop, a funding cliff), capped per day
//   GET             /v1/frontier/models      the model ids the OpenAI key can reach, and which are priced
//   POST            /v1/frontier/responses   one frontier call, reserved and settled against the month
//   GET             /v1/claude/models        the Claude model ids the Anthropic key can reach, and which are priced
//   POST            /v1/claude/messages      one Claude call, reserved and settled against the funded total (the
//                                            kill switch stops it; lib/claude.mjs)
//   GET             /v1/claude/request/<id>  what became of the House's Claude call <id> (its X-LTCM-Request)
//   POST            /v1/typesafe/systemone  funded Jev judgments, with durable request identities
//   POST            /v1/web/fetch            one public page's text for research, capped per day (lib/fetch.mjs)
//   GET             /v1/research/search      the research library: arXiv papers posted before 2025 for plain keywords
//   GET             /v1/research/read        one pinned version's metadata and a window of its text (lib/library.mjs)
//   GET             /v1/research/health      the library's pace, lease and day's count (also `library` in /v1/health)
//   POST            /v1/github/pr            a proposal becomes a branch and a pull request, never a push
//   GET             /v1/github/pr/<n>        that pull request and its CI, so the VM can watch it
//   GET             /v1/github/pr/<n>/failures  why CI refused it: failed runs and their annotations
//   GET             /v1/github/pr/<n>/files?head_sha=  the exact change at that head, file by file (lib/pulls.mjs; V3-A)
//   POST            /v1/github/close         close one engineer pull request at its exact head (lib/pulls.mjs; V3-A)
//   POST            /v1/github/docs          one desk page committed to main under docs/runs/desk/ (lib/desk.mjs; V3-A)
//   POST            /v1/github/review        the automated reviewer's verdict on one engineer pull request's exact head
//   POST            /v1/github/merge         squash-merge one engineer pull request inside lib/merge.mjs's walls (V3-A)
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
// propose its own repair. Until V3-A there was no merge route. Since V3-A (the owner's decision D5)
// one exists for the engineer's research-class pull requests alone: an `engineer/` branch, at an
// exact head commit, on green `checks.yml` jobs and a recorded approve, touching no protected path
// (lib/protected.mjs), at most two a New York day (lib/merge.mjs). Every other branch is still
// merged by a repository workflow or by the owner. The desk's docs route commits one page under
// docs/runs/desk/ and nothing else (lib/desk.mjs). The merge alone is stopped by the kill switch
// (gate.mergeReserve, 423 `kill_switch`): with auto_update on, a merge is a deploy, and the owner's
// stop must freeze the code the owner is looking at. Proposals, reviews, closes and docs stay open.
//
// `gate` is the Durable Object stub (or, in tests, the gate itself): every method is awaited, so
// the same router works against both.

import { json, fail, authorized, readBody } from './http.mjs';
import { composeNotice, NOTICE_KINDS, FROM, TO } from './email.mjs';
import {
  createsOrder, notional, PURPOSE_HEADER, allowedVenuePath, isOptionSymbol, alpacaShapeError,
  admittedStructures, isMultiLegOrder, structureNotional, practiceOrderError, closeLegsHeldError, closedLegRows,
  shortCloseBody, longCloseBody, singleLegOpenError, realStockClose, CREDIT_STRUCTURES,
} from './caps.mjs';
import * as kalshi from './kalshi.mjs';
import * as alpaca from './alpaca.mjs';
import * as frontier from './frontier.mjs';
import * as claude from './claude.mjs';
import * as equity from './equity.mjs';
import * as account from './account.mjs';
import * as typesafe from './typesafe.mjs';
import * as web from './fetch.mjs';
import * as library from './library.mjs';
import * as github from './github.mjs';
import * as desk from './desk.mjs';
import * as merge from './merge.mjs';
import * as pulls from './pulls.mjs';

export const VENUES = ['kalshi', 'alpaca', 'alpaca-paper'];
//: Venues that hold no real money. Their orders are never metered and the kill switch does not
//: stop them: the paper league must keep learning while real trading is halted.
export const PAPER_VENUES = ['alpaca-paper'];
//: The venue whose path rules a venue shares.
const rulesOf = venue => (venue === 'alpaca-paper' ? 'alpaca' : venue);
//: The real Alpaca account's positions, read before a real structure close is admitted (Sept 25, 2026), reused this long:
//: briefly, so a burst of closes reads them once and a leg sold a moment ago is not counted for long. A close admitted from
//: the cached reading takes its own legs out of it (`caps.closedLegRows`), so the same legs are not closed twice from it.
const POSITIONS_CACHE_MS = 5_000;
let positionsCache = null;
//: The status of a real structure close refused because the account's positions could not be read: a 4xx, never a 5xx.
//: Nothing was sent, and the House's adapter reads a 5xx as "the venue may have the order" (`VenueUnavailable`), which the
//: Book holds as `unknown` for a minute or more of polls, while a 4xx is a refusal it sends again at its next tick
//: (`RejectedOrder`; the review of g/money, Sept 25, 2026). 424: the order failed on the positions read it depends on.
const POSITIONS_UNREAD_STATUS = 424;
//: The status of a real OPENING order refused because the account's equity could not be read in time (Sept 26, 2026 (the
//: options-swarm run, Wave 5)): a 503 the House sends again, with nothing reserved or sent. Only opens wait on the reading.
const EQUITY_UNREAD_STATUS = 503;
const EQUITY_RETRY = { 'Retry-After': '30' };

/**
 * A refusal made before anything is forwarded, naming why in `cap` (Sept 26, 2026 (the options-swarm run, Wave 5), the
 * review's m8/m12). Every such refusal on a venue route carries one, a 5xx above all: the House reads a 5xx without a
 * `cap` as a venue that may hold the order, and one with a `cap` as a refusal that sent nothing. The one 5xx that names
 * no cap is the answer that never came after dispatch (a 502): that one may be an order.
 */
const refuse = (message, status, cap, headers = {}) => json({ error: message, cap }, status, headers);
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

export async function route(request, env, { gate, fetcher = fetch, now = Date.now, mailer = null, waitUntil = null, sleep } = {}) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '') || '/';

  // Who is calling (V3-A, WP8: the admin log). The owner's token is accepted at /v1/unkill and /v1/kill (stopping is
  // never gated), the runtime token everywhere but /v1/unkill. Every call that presents the owner's token, and every
  // kill and unkill, is written to the admin log with its time, the caller's kind, the route and the answer; a call
  // with no accepted token at the switch is counted. Nothing of the request but its route and method is kept.
  const ownerAction = path === '/v1/unkill';
  const switchAction = ownerAction || path === '/v1/kill';
  const admin = authorized(request, env.GATEWAY_ADMIN_TOKEN);
  const runtime = authorized(request, env.GATEWAY_TOKEN);
  const caller = admin ? 'admin' : runtime ? 'runtime' : 'none';
  const allowed = ownerAction ? admin : path === '/v1/kill' ? admin || runtime : runtime;
  const audit = async status => {
    try {
      await gate.adminRecord({ caller, action: 'call', route: path, method: request.method, status, at: now() });
    } catch {
      // The log is a record, never a gate on an answer that refuses or reads.
    }
  };
  if (!allowed) {
    // A caller with no accepted token is never written: the Gate serializes every order, and a stranger's flood at the
    // public switch must not queue writes in front of them.
    if (caller !== 'none' && (admin || switchAction)) await audit(401);
    return fail('Unauthorized.', 401, { 'WWW-Authenticate': 'Bearer' });
  }

  if (path === '/v1/health') {
    if (request.method !== 'GET' && request.method !== 'HEAD') return fail('Method not allowed.', 405, { Allow: 'GET' });
    // The health read reports the stored equity reading and never refreshes it: the House reads its
    // kill switch here on the order path and treats a slow answer as the switch engaged, and a
    // refresh reads both venues one after the other. The frontier path refreshes it (ten minutes).
    return json(await gate.status());
  }
  if (switchAction) {
    if (request.method !== 'POST') {
      if (admin) await audit(405);
      return fail('Method not allowed.', 405, { Allow: 'POST' });
    }
    try {
      // The switch and its admin-log entry in one step: a release whose entry cannot be written releases nothing.
      await gate.setKill(path === '/v1/kill', now(), { caller, route: path, method: request.method });
    } catch {
      return json({ error: 'The kill switch could not be changed; it is as it was.', cap: 'setup' }, 503);
    }
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
      const table = frontier.priceTable(env);
      return json({ models: (data?.data || []).map(row => row?.id).filter(id => typeof id === 'string').sort(), priced: Object.keys(table),
        flex: Object.keys(table).filter(model => table[model].flex) });
    } catch {
      return fail('The frontier provider did not answer.', 502);
    }
  }
  if (path === '/v1/frontier/responses') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return frontierCall(request, env, { gate, fetcher, now });
  }

  if (path === '/v1/claude/models') {
    // Free and read-only: which models the Anthropic key can reach, so a price is never set on a guess.
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    if (!env.CLAUDE_API_KEY) return json({ error: 'Claude is not configured.', cap: 'setup' }, 503);
    try {
      const upstream = await fetcher(`${claude.HOST}/v1/models?limit=100`, {
        method: 'GET', headers: claudeHeaders(env), redirect: 'manual', signal: AbortSignal.timeout(20000),
      });
      const data = await upstream.json().catch(() => null);
      if (!upstream.ok) return fail(`Anthropic answered HTTP ${upstream.status}.`, 502);
      return json({ models: (data?.data || []).map(row => row?.id).filter(id => typeof id === 'string').sort(),
        priced: Object.keys(claude.priceTable(env)) });
    } catch {
      return fail('Anthropic did not answer.', 502);
    }
  }
  if (path === '/v1/claude/messages') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return claudeCall(request, env, { gate, fetcher, now, waitUntil });
  }
  const claudeRequest = /^\/v1\/claude\/request\/([A-Za-z0-9:._-]{1,160})$/.exec(path);
  if (claudeRequest) {
    // Free and read-only: the House trues up a hold it could not settle from its own answer.
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    return json(await gate.claudeRequest(decodeURIComponent(claudeRequest[1])));
  }

  if (path === '/v1/typesafe/systemone') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return typesafeCall(request, env, { gate, fetcher, now });
  }

  if (path === web.PATH) {
    // Research reads one public page; it moves no money, so the kill switch does not stop it.
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return web.webFetch(request, env, { gate, fetcher, now });
  }

  if (library.isLibraryPath(path)) {
    // The research library (Sept 29, 2026): arXiv before 2025, paced to arXiv's terms; it moves no money, so the kill
    // switch does not stop it.
    return library.libraryRoute(request, env, { gate, fetcher, now, ...(sleep ? { sleep } : {}) });
  }

  if (path === '/v1/github/pr') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return proposePull(request, env, { gate, fetcher, now });
  }
  if (path === '/v1/github/docs') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return deskDocs(request, env, { gate, fetcher, now });
  }
  if (path === '/v1/github/review') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return recordReview(request, env, { gate, fetcher, now });
  }
  if (path === '/v1/github/merge') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return mergePull(request, env, { gate, fetcher, now });
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
  if (path === '/v1/github/close') {
    if (request.method !== 'POST') return fail('Method not allowed.', 405, { Allow: 'POST' });
    return closeEngineerPull(request, env, { fetcher });
  }
  const changes = /^\/v1\/github\/pr\/([1-9][0-9]{0,8})\/files$/.exec(path);
  if (changes) {
    // Read-only and free: the exact diff at one head, for the automated reviewer (lib/pulls.mjs).
    if (request.method !== 'GET') return fail('Method not allowed.', 405, { Allow: 'GET' });
    const account = github.configured(env);
    if (!account) return fail('GitHub is not configured.', 503);
    const asked = pulls.admitFilesQuery(url);
    if (asked.error) return fail(asked.error, asked.status);
    const found = await pulls.pullFiles({ ...account, number: Number(changes[1]), headSha: asked.headSha, fetcher });
    return found.error ? refusedWith(found) : json(found);
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

  // --- the practice account's order shapes (Sept 25, 2026) --------------------------------------
  // Never metered, but an OPTION order is held to the defined-risk shapes (`caps.practiceOrderError`):
  // until today an order to the practice account was forwarded with no check at all. Stock and
  // crypto orders pass as before.
  if (PAPER_VENUES.includes(target.venue) && createsOrder(rulesOf(target.venue), request.method, target.path)) {
    let parsed = null;
    try {
      parsed = JSON.parse(body.text || '');
    } catch {
      return fail('An order body must be JSON.', 400);
    }
    const refusal = practiceOrderError(parsed);
    if (refusal) return fail(refusal, 400);
  }

  // --- caps, before anything is signed or sent -------------------------------------------------
  let reservation = null;
  if (!PAPER_VENUES.includes(target.venue) && createsOrder(target.venue, request.method, target.path)) {
    let parsed = null;
    try {
      parsed = body.text ? JSON.parse(body.text) : null;
    } catch {
      return fail('An order body must be JSON.', 400);
    }
    let order;
    if (target.venue === 'alpaca') {
      // The real Alpaca account (Sept 26, 2026 (the options-swarm run, Wave 5)): `realOrder` decides, from the order
      // itself and never from the caller's header, whether it opens or closes, and reads what the decision needs.
      order = await realOrder(parsed, env, { gate, fetcher, now });
      if (order.response) return order.response;
    } else {
      const exit = String(request.headers.get(PURPOSE_HEADER) || '').toLowerCase() === 'exit';
      const priced = notional(target.venue, parsed, { exit });
      if (priced.error) return fail(priced.error, 400);
      order = { micro: priced.micro, exit, credit: false, closeRows: null };
    }
    const decision = await gate.reserve({ micro: String(order.micro), exit: order.exit, venue: target.venue, credit: order.credit });
    if (!decision.ok) {
      return json({ error: decision.error, ...(decision.cap ? { cap: decision.cap } : {}) }, decision.status,
        decision.status === EQUITY_UNREAD_STATUS ? EQUITY_RETRY : {});
    }
    reservation = decision;
    if (order.closeRows && positionsCache) {
      // The close goes: its legs leave the cached reading, so a second close of them within the cache is refused.
      positionsCache = { ...positionsCache, positions: [...positionsCache.positions, ...order.closeRows] };
    }
  }

  // --- sign and forward ------------------------------------------------------------------------
  let outbound;
  try {
    outbound = await sign(target, request, env, { now: now() });
  } catch (error) {
    if (reservation) await gate.refund(reservation);
    return refuse(`Gateway credentials for ${target.venue} are unusable: ${error.message}`, 503, 'credentials');
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

/**
 * One order to the REAL Alpaca account, read before anything is reserved (Sept 26, 2026 (the options-swarm run, Wave 5)):
 * `{ micro, exit, credit, closeRows }` for the gate, or `{ response }`, the refusal to answer with.
 *
 *  - A multi-leg OPEN of an admitted type (`OPTION_STRUCTURES_REAL`) and a single-leg `buy_to_open` of an admitted right
 *    (`long_call`, `long_put`: none as deployed, the review's m7/m15) are OPENING orders, whatever `X-LTCM-Purpose` says: metered at their maximum loss (the structure's, or premium x 100 x qty) against the
 *    caps by maximum loss, which need the account's equity read by this Worker in the last EQUITY_CAP_MAX_AGE_MS
 *    (`account.refreshAccountEquity`). No such reading refuses the open (a 503 the House sends again); a credit type opens
 *    only at CREDIT_MIN_EQUITY_USD or more (the gate).
 *  - Everything else that passes is an EXIT, read no equity and meets no dollar cap: a multi-leg close, a single-leg
 *    `buy_to_close` and a single-leg `sell_to_close` (each admitted only when the account holds what it closes; the
 *    sell_to_close since the review's m14), and a stock order that closes shares the account holds
 *    (`caps.realStockClose`): the one stock order the real account may send. Every other stock or crypto order is refused.
 *  - Every refusal names its `cap` when it is a 424 or a 5xx (`refuse`): nothing was sent.
 *
 * Until today the exit header decided what a real order was; for the real account it decides nothing now. The House sets
 * it on its sells and its buy-backs, which are exits here by their own shape.
 */
async function realOrder(parsed, env, { gate, fetcher, now }) {
  // The structure types the real account may OPEN (`OPTION_STRUCTURES_REAL`).
  const structures = admittedStructures(env);
  // A bracket, stop, trailing or symbol-less order is refused before anything is read. A multi-leg order is read by its
  // own rules instead, whatever the list: an open of a type the list does not admit is refused there, and a close of any
  // defined-risk type is admitted only when the account holds its legs (below). Until Sept 25, 2026 (the review of
  // g/money, MAJOR) "off" refused every multi-leg order, closes included, and stranded a held structure into expiry.
  const multi = isMultiLegOrder(parsed);
  const shape = multi ? structureNotional(parsed, structures).error : alpacaShapeError(parsed);
  if (shape) return { response: fail(shape, 400) };
  // A single contract bought to open is a long_call or a long_put, admitted only when OPTION_STRUCTURES_REAL names it
  // (Sept 26, 2026, Wave 5, the review's m7/m15): until today every single-leg buy_to_open went, though the real account
  // trades only the types the list names. Refused before anything is read.
  const single = multi ? null : singleLegOpenError(parsed, structures);
  if (single) return { response: fail(single, 400) };

  if (!multi && !isOptionSymbol(parsed.symbol)) {
    // A stock (or crypto) order: only the close of shares the account holds, read from its signed positions. No quote is
    // read: it is an exit, reserved at one micro-dollar like any real close, and a quote could only delay it.
    const close = realStockClose(parsed);
    if (close.error) return { response: fail(close.error, 400) };
    const held = await realPositions(env, { fetcher, now });
    if (held.error) return { response: refuse(`Cannot check that the real account holds these shares: ${held.error}.`, POSITIONS_UNREAD_STATUS, 'positions') };
    const refusal = closeLegsHeldError(close.body, held.positions);
    if (refusal) return { response: fail(refusal, 400) };
    return { micro: 1n, exit: true, credit: false, closeRows: closedLegRows(close.body) };
  }

  const priced = notional('alpaca', parsed, { structures });
  if (priced.error) return { response: fail(priced.error, 400) };
  if (priced.structure && !priced.opening) {
    // A structure's open or close is read from its legs' position_intent, never from the caller's header. A close takes
    // risk off and is metered at zero; the gate refuses a zero reservation and counts every order, so a close holds the
    // least amount it records, one micro-dollar, as an exit: the kill switch and the day's order count still stop it,
    // the dollar caps do not. Since Sept 25, 2026 (the route's review, MINOR 1) a close is admitted only when the real
    // account HOLDS every leg it closes, long legs long and short legs short (`caps.closeLegsHeldError`), read from the
    // account's positions. A close of ANY defined-risk type is admitted so, whatever OPTION_STRUCTURES_REAL lists (the
    // list gates opens only). Positions that cannot be read admit no close (a 4xx, `POSITIONS_UNREAD_STATUS`): the House
    // sends it again at its next tick.
    const held = await realPositions(env, { fetcher, now });
    if (held.error) return { response: refuse(`Cannot check that the real account holds this structure's legs: ${held.error}.`, POSITIONS_UNREAD_STATUS, 'positions') };
    const refusal = closeLegsHeldError(parsed, held.positions);
    if (refusal) return { response: fail(refusal, 400) };
    return { micro: 1n, exit: true, credit: false, closeRows: closedLegRows(parsed) };
  }
  if (priced.shortClose) {
    // A single-leg option buy_to_close (Sept 25, 2026, the review of Deploy G, MAJOR 2): the book's buy-back of a short
    // leg a broken structure left on the real account (`league/book.py` `_close_break_units`). It is an exit whatever the
    // header says, metered at one micro-dollar like a structure close (the kill switch and the day's order count still
    // stop it), and admitted ONLY when the account's signed positions show that contract held SHORT for at least its qty:
    // read as a one-leg close (`caps.shortCloseBody`) by the same rule as a structure's legs, so a buy "to close" of a
    // contract not held short, which would open a long position under another name, is refused before anything is
    // reserved. Unread positions admit nothing (a 4xx the House retries).
    const shortClose = shortCloseBody(parsed);
    const held = await realPositions(env, { fetcher, now });
    if (held.error) return { response: refuse(`Cannot check that the real account holds this contract short: ${held.error}.`, POSITIONS_UNREAD_STATUS, 'positions') };
    const refusal = closeLegsHeldError(shortClose, held.positions);
    if (refusal) return { response: fail(refusal, 400) };
    return { micro: 1n, exit: true, credit: false, closeRows: closedLegRows(shortClose) };
  }
  if (!priced.structure && parsed.position_intent === 'sell_to_close') {
    // A single-leg option sell_to_close (Sept 26, 2026, Wave 5, the review's m14): an exit, metered at its premium as
    // before, and admitted only when the account's signed positions show that contract held LONG for at least its qty
    // (available), by the same rule as every real close. Until today it was trusted to the venue, and a margin account
    // may take a sale of what it does not hold long as a sale to open: a naked short.
    const longClose = longCloseBody(parsed);
    const held = await realPositions(env, { fetcher, now });
    if (held.error) return { response: refuse(`Cannot check that the real account holds this contract long: ${held.error}.`, POSITIONS_UNREAD_STATUS, 'positions') };
    const refusal = closeLegsHeldError(longClose, held.positions);
    if (refusal) return { response: fail(refusal, 400) };
    return { micro: priced.micro, exit: true, credit: false, closeRows: closedLegRows(longClose) };
  }
  // What is left is an OPEN: a structure of an admitted type, or a single-leg buy_to_open of an admitted right
  // (`caps.optionNotional` admits no other single-leg intent on the real account; anything else is refused here).
  if (!priced.structure && parsed.position_intent !== 'buy_to_open') {
    return { response: fail('A single-leg option order on the real account is a buy_to_open, a sell_to_close or a buy_to_close.', 400) };
  }
  const maxAgeMs = account.maxLossCaps(env).maxAgeMs;
  const reading = await account.refreshAccountEquity(env, gate, { fetcher, now });
  if (account.freshEquity(reading, now(), maxAgeMs) === null) {
    const why = reading && reading.ok !== true ? String(reading.error || 'unreadable') : 'no reading';
    return {
      response: refuse(`Cannot read the real account's equity (${why}): an opening order is sized against a reading no older ` +
        `than ${Math.round(maxAgeMs / 1000)} seconds, so nothing was sent. Send it again.`, EQUITY_UNREAD_STATUS, 'equity', EQUITY_RETRY),
    };
  }
  return { micro: priced.micro, exit: false, credit: CREDIT_STRUCTURES.includes(priced.structure), closeRows: null };
}

/**
 * The real Alpaca account's positions (`GET v2/positions`, signed like every other call), reused for `POSITIONS_CACHE_MS`
 * (`env.POSITIONS_CACHE_MS` overrides; 0 reads them every time): `{positions}` or `{error}`. The read never follows a
 * redirect (it carries the REAL account's key headers): a 3xx is an answer that cannot be read, and admits no close.
 */
async function realPositions(env, { fetcher, now }) {
  const cacheMs = Number(env.POSITIONS_CACHE_MS ?? POSITIONS_CACHE_MS);
  if (cacheMs <= 0) positionsCache = null;
  if (cacheMs > 0 && positionsCache && positionsCache.expires > Date.now()) return { positions: positionsCache.positions };
  let answer;
  try {
    const signed = await sign({ venue: 'alpaca', path: 'v2/positions' }, new Request('https://x/v2/positions', { method: 'GET' }), env, { now: now() });
    answer = await fetcher(signed.url, { method: 'GET', headers: signed.headers, signal: AbortSignal.timeout(8000), redirect: 'manual' });
  } catch (error) {
    return { error: error?.name || 'fetch failed' };
  }
  if (!answer.ok) return { error: `venue HTTP ${answer.status}` };
  let positions;
  try {
    positions = await answer.json();
  } catch {
    return { error: 'an unreadable venue answer' };
  }
  if (!Array.isArray(positions)) return { error: 'the venue\'s positions were not a list' };
  if (cacheMs > 0) positionsCache = { positions, expires: Date.now() + cacheMs };
  return { positions };
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
  // The role names its output ceiling (`FRONTIER_ROLE_MAX_OUTPUT`, Sept 26, 2026 (the options-swarm run, Wave 5)).
  const admitted = frontier.admit(parsed, env, { role: request.headers.get(frontier.ROLE_HEADER) });
  if (admitted.error) return fail(admitted.error, admitted.status);
  const bytes = new TextEncoder().encode(body.text).length;
  await equity.refresh(env, gate, { fetcher, now });  // profit-indexed cap: the accounts read at most every ten minutes
  const hold = await gate.frontierReserve({ micro: String(frontier.worstCase(admitted.price, bytes, admitted.maxOutput)), at: now() });
  if (!hold.ok) return json({ error: hold.error, ...(hold.cap ? { cap: hold.cap } : {}) }, hold.status);
  const agent = request.headers.get(frontier.AGENT_HEADER);
  const settle = actual => gate.frontierSettle({ month: hold.month, reserved: hold.micro, actual, agent, tracked: hold.tracked === true, at: now() });
  let upstream, text;
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
    // Read inside the guard (Sept 24, 2026): an answer cut off mid-body used to throw past the
    // settle, the Worker answered "error code: 1101", and the hold was left in flight for good.
    text = await upstream.text();
  } catch {
    // Nothing came back, or not all of it. The provider may still bill a call it received, so the hold stays.
    await settle(null);
    return fail('The frontier model did not answer.', 502);
  }
  let actual = null;
  let tier = null;
  if (upstream.ok) {
    try {
      const answer = JSON.parse(text);
      // Flex (Sept 26, 2026, Wave 5) is settled at its own rates only when the call asked for it AND the answer says it
      // was served on it; OpenAI may serve a flex request on another tier, and then it is billed at the standard rates.
      tier = admitted.flex && answer?.service_tier === 'flex' ? 'flex' : 'default';
      actual = frontier.actualCost(tier === 'flex' ? admitted.flex : admitted.price, answer?.usage);
    } catch { actual = null; }
  } else if (upstream.status >= 400 && upstream.status < 500) {
    // Refused by the provider before any generation: nothing was billed. A 429 is flex's own capacity refusal
    // ("resource unavailable", no charge), settled here at zero like every other 4xx.
    actual = 0n;
  } else if (frontier.unprocessed(upstream.status, text)) {
    actual = 0n;  // the provider's own capacity refusal, turned away before any work (frontier.unprocessed)
  }
  const settled = await settle(actual === null ? null : String(actual));
  return new Response(text, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'application/json; charset=utf-8',
      'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
      ...(settled?.cost_usd ? { 'X-LTCM-Cost-USD': settled.cost_usd } : {}),
      ...(tier ? { 'X-LTCM-Billed-Tier': tier } : {}),
    },
  });
}

/** The headers every Anthropic call carries: the key is added here, on the way out, and never comes back. */
function claudeHeaders(env, { stream = false } = {}) {
  return { 'Content-Type': 'application/json', Accept: stream ? 'text/event-stream' : 'application/json', 'x-api-key': env.CLAUDE_API_KEY,
    'anthropic-version': claude.API_VERSION, 'User-Agent': 'ltcm-gateway/1.0' };
}

/**
 * One Claude call (Sept 26, 2026, the swarm sprint): refused while the kill switch is engaged, reserved at its worst
 * case against the funded total, forwarded, and settled from Anthropic's usage block. A refusal (`stop_reason`
 * "refusal", an HTTP 200) and a truncated answer ("max_tokens") are billed and settle at their usage; a 4xx settles at
 * zero (refused before any generation); so does a 5xx without a usage block, and so does a call whose request never
 * got an answer (the owner's rule for this meter: Anthropic bills completed work, and the account's own prepaid balance
 * is the backstop). Once Anthropic's headers arrived, though, the call ran: a body cut off mid-read, or a 2xx whose
 * usage does not read, keeps its whole hold as spent (unknown is not free), as the frontier's does. The House's
 * X-LTCM-Request id files the outcome (`gate.claudeRequest`).
 */
async function claudeCall(request, env, { gate, fetcher, now, waitUntil = null }) {
  if (!env.CLAUDE_API_KEY) return json({ error: 'Claude is not configured.', cap: 'setup' }, 503);
  const body = await readBody(request, claude.MAX_REQUEST_BYTES);
  if (body.error) return fail(body.error, 413);
  let parsed;
  try {
    parsed = JSON.parse(body.text || '');
  } catch {
    return fail('The request must be JSON.', 400);
  }
  const admitted = claude.admit(parsed, env);
  if (admitted.error) return fail(admitted.error, admitted.status);
  // What leaves is the body that was checked (Sept 29, 2026): the parse `admit` read, serialized again. Forwarding the
  // raw text would let a body with a key given twice pass the check on its last value (JSON.parse keeps the last) and
  // reach Anthropic with its first. The worst case is sized from these bytes too; compact JSON is never longer than
  // the House's own `json.dumps`, so the House's hold stays at or above this one.
  const forwarded = JSON.stringify(parsed);
  const bytes = new TextEncoder().encode(forwarded).length;
  const tag = claude.requestId(request.headers.get(claude.REQUEST_HEADER));
  const hold = await gate.claudeReserve({ micro: String(claude.worstCase(admitted.price, bytes, admitted.maxTokens)), request: tag, at: now() });
  if (!hold.ok) return json({ error: hold.error, ...(hold.cap ? { cap: hold.cap } : {}) }, hold.status);
  const agent = request.headers.get(frontier.AGENT_HEADER);
  const role = request.headers.get(frontier.ROLE_HEADER);
  const settle = (actual, stop = null, geo = null) =>
    gate.claudeSettle({ id: hold.id, reserved: hold.micro, actual, agent, role, stop, geo, at: now() });
  let upstream, text;
  try {
    upstream = await fetcher(claude.HOST + claude.PATH, {
      method: 'POST', headers: claudeHeaders(env, { stream: admitted.stream }), body: forwarded, redirect: 'manual',
      // Just under the House's own 600-second read, as the frontier's; a stream just over it (the House gives up first).
      signal: AbortSignal.timeout(admitted.stream ? claude.STREAM_TIMEOUT_MS : 570000),
    });
  } catch {
    const settled = await settle('0', 'no_answer');
    return json({ error: 'Anthropic did not answer.' }, 502, { 'X-LTCM-Cost-USD': settled.cost_usd });
  }
  if (admitted.stream && upstream.ok) return claudeStream(upstream, { admitted, settle, waitUntil });
  try {
    text = await upstream.text();
  } catch {
    // Anthropic answered and then the body was cut off: the call ran and may be billed. Its whole hold stays spent.
    const settled = await settle(null, 'body_cut');
    return json({ error: 'Anthropic\'s answer was cut off; its worst case stays on the meter.' }, 502,
      { 'X-LTCM-Cost-USD': settled.cost_usd, 'X-LTCM-Cost-Known': 'false' });
  }
  let answer = null;
  try { answer = JSON.parse(text); } catch { answer = null; }
  let actual, stop = null;
  if (upstream.ok) {
    actual = claude.actualCost(admitted.price, answer?.usage);
    stop = typeof answer?.stop_reason === 'string' ? answer.stop_reason : null;
  } else if (upstream.status >= 400 && upstream.status < 500) {
    actual = 0n;  // refused before any generation: nothing billed
    stop = `http_${upstream.status}`;
  } else {
    actual = claude.actualCost(admitted.price, answer?.usage) ?? 0n;  // a 5xx is billed only for the usage it reports
    stop = `http_${upstream.status}`;
  }
  const geo = typeof answer?.usage?.inference_geo === 'string' ? answer.usage.inference_geo : null;
  const settled = await settle(actual === null ? null : String(actual), stop, geo);
  return new Response(text, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'application/json; charset=utf-8',
      'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
      ...(settled?.cost_usd ? { 'X-LTCM-Cost-USD': settled.cost_usd } : {}),
      ...(actual === null ? { 'X-LTCM-Cost-Known': 'false' } : {}),
    },
  });
}

/**
 * A streamed Claude call's answer (Sept 27, 2026): Anthropic's events go to the House as they arrive, so no hop waits in
 * silence (Cloudflare gives up on a silent origin after 100 seconds: HTTP 524), and are metered on the way
 * (`claude.StreamMeter`). When the stream ends the call is settled, and one last event, `ltcm.cost`
 * (`{ cost_usd, known, stop }`), tells the House what the meter booked. A stream that broke after its headers, or ended
 * without `message_stop`, keeps its whole hold (unknown is not free: the 30-minute sweep and `/v1/claude/request/<id>`
 * reconcile it); an `error` event settles at the usage seen so far, or unknown before any. A House that went away
 * stops the stream (Anthropic's generation with it) and the call settles unknown unless its usage was complete. The
 * settling runs under `waitUntil`, so it outlives the response.
 */
function claudeStream(upstream, { admitted, settle, waitUntil }) {
  const meter = new claude.StreamMeter();
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  let gone = false, reader = null;
  // The House closing its end is noticed at once, not at the next write: a quiet Anthropic (the model thinking) could
  // otherwise hold the pump past Cloudflare's grace for waitUntil, and the call would never settle. Cancelling
  // Anthropic's stream ends the read below, and the call settles as `house_gone` at its whole hold.
  writer.closed.catch(() => {
    gone = true;
    reader?.cancel().catch(() => {});
  });
  const pump = (async () => {
    const parser = claude.sseParser();
    let broken = false;
    try {
      reader = upstream.body.getReader();
      if (gone) await reader.cancel().catch(() => {});
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const event of parser.push(value)) meter.observe(event);
        try {
          await writer.write(value);
        } catch {
          gone = true;  // the House closed its end
          try { await reader.cancel(); } catch { /* already closed */ }
          break;
        }
      }
      for (const event of parser.end()) meter.observe(event);
    } catch {
      broken = true;
    }
    const outcome = meter.settlement(admitted.price, { broken: broken || gone });
    const stop = gone && !meter.stopped ? 'house_gone' : outcome.stop;
    let settled = null;
    try {
      settled = await settle(outcome.cost === null ? null : String(outcome.cost), stop, meter.geo);
    } catch { /* the hold stays; the sweep and the House's true-up reconcile it */ }
    if (gone) return;
    try {
      const tail = { type: 'ltcm.cost', cost_usd: settled?.cost_usd ?? null, known: outcome.cost !== null && settled !== null, stop };
      // The blank line first ends any event a broken stream left half-sent, so the tail always reads as its own event.
      await writer.write(new TextEncoder().encode(`\n\nevent: ltcm.cost\ndata: ${JSON.stringify(tail)}\n\n`));
      await writer.close();
    } catch { /* the House went away at the end */ }
  })();
  if (typeof waitUntil === 'function') waitUntil(pump);
  return new Response(readable, {
    status: upstream.status,
    headers: { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
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

/** A JSON body read within `limit` bytes: `{ parsed }`, or `{ response }`, the refusal to answer with. */
async function jsonBody(request, limit) {
  const body = await readBody(request, limit);
  if (body.error) return { response: fail(body.error, 413) };
  try {
    return { parsed: JSON.parse(body.text || '') };
  } catch {
    return { response: fail('The request must be JSON.', 400) };
  }
}

/** A refusal that names its rule (`refused`) or cap, as the docs, review and merge routes answer. */
const refusedWith = (outcome, extra = {}) => json({
  error: outcome.error, ...(outcome.refused ? { refused: outcome.refused } : {}), ...(outcome.cap ? { cap: outcome.cap } : {}), ...extra,
}, outcome.status || 502, outcome.status === 429 ? { 'Retry-After': '3600' } : {});

/**
 * One desk page committed to main (V3-A, WP8; lib/desk.mjs): admitted by its path, size, text and message first, then
 * compared with what main holds (the same text again commits nothing and takes no place), then one of the day's
 * DOCS_PER_DAY places, then GitHub's Contents API. A place is given back only when GitHub answered no.
 */
async function deskDocs(request, env, { gate, fetcher, now }) {
  const account = github.configured(env);
  if (!account) return fail('GitHub is not configured.', 503);
  const body = await jsonBody(request, desk.MAX_REQUEST_BYTES);
  if (body.response) return body.response;
  const doc = desk.admitDoc(body.parsed, env);
  if (doc.error) return refusedWith(doc);
  if (await gate.docsToday(now()) >= desk.DOCS_PER_DAY) {
    return refusedWith({ status: 429, cap: 'docs_day', error: `Today's cap of ${desk.DOCS_PER_DAY} docs commits is already reached.` });
  }
  const held = await desk.readDoc({ ...account, path: doc.path, fetcher });
  if (held.error) return refusedWith(held);
  if (held.sha === desk.blobSha(doc.content)) return json({ ok: true, committed: false, unchanged: true, path: doc.path });
  const hold = await gate.docsReserve({ path: doc.path, at: now() });
  if (!hold.ok) return refusedWith(hold);
  const result = await desk.putDoc({ ...account, doc, sha: held.sha, fetcher });
  const outcome = result.committed === true ? 'committed' : result.committed === false ? 'refused' : 'unknown';
  try {
    await gate.docsSettle({ day: hold.day, id: hold.id, outcome, commit: result.commit ?? null, at: now() });
  } catch {
    // The place stays taken; the record of what became of it is the only thing lost.
  }
  if (result.committed !== true) return refusedWith({ ...result, refused: result.committed === null ? 'no_answer' : 'github' });
  return json({ ok: true, committed: true, path: doc.path, commit: result.commit, docs_today: hold.count });
}

/**
 * The automated reviewer's verdict (V3-A, WP8; lib/merge.mjs): recorded for one engineer pull request at its exact
 * current head, read from GitHub first. A reject is final for that commit.
 */
async function recordReview(request, env, { gate, fetcher, now }) {
  const account = github.configured(env);
  if (!account) return fail('GitHub is not configured.', 503);
  const body = await jsonBody(request, merge.MAX_REQUEST_BYTES);
  if (body.response) return body.response;
  const review = merge.admitReview(body.parsed);
  if (review.error) return refusedWith(review);
  const target = await merge.reviewTarget({ ...account, number: review.pr, headSha: review.head_sha, fetcher });
  if (target.error) return refusedWith(target);
  const recorded = await gate.reviewRecord({ pr: review.pr, sha: review.head_sha, verdict: review.verdict, reasons: review.reasons, at: now() });
  if (!recorded.ok) return refusedWith(recorded);
  return json({ ok: true, pr: review.pr, head_sha: review.head_sha, verdict: recorded.verdict, at: recorded.at,
    ...(recorded.duplicate ? { duplicate: true } : {}) });
}

/** Close one engineer pull request at its exact head (V3-A; lib/pulls.mjs): a superseded revision or a rejected one. */
async function closeEngineerPull(request, env, { fetcher }) {
  const account = github.configured(env);
  if (!account) return fail('GitHub is not configured.', 503);
  const body = await jsonBody(request, merge.MAX_REQUEST_BYTES);
  if (body.response) return body.response;
  const asked = merge.admitMerge(body.parsed);
  if (asked.error) return refusedWith(asked);
  const result = await pulls.closePull({ ...account, number: asked.pr, headSha: asked.head_sha, fetcher });
  if (result.error) return refusedWith(result);
  return json({ ok: true, closed: true, pr: asked.pr, head_sha: asked.head_sha });
}

/**
 * Squash-merge one engineer pull request (V3-A, WP8; lib/merge.mjs). The Gate's checks first (the day's count, an
 * approve and no reject on the exact commit), then GitHub's (the pull request, its files, its CI), then one of the
 * day's MERGES_PER_DAY places, then the merge of exactly that commit. A place is given back only when GitHub answered
 * no; a merge nothing answered stays counted (`merged: "unknown"`).
 */
async function mergePull(request, env, { gate, fetcher, now }) {
  const account = github.configured(env);
  if (!account) return fail('GitHub is not configured.', 503);
  const body = await jsonBody(request, merge.MAX_REQUEST_BYTES);
  if (body.response) return body.response;
  const asked = merge.admitMerge(body.parsed);
  if (asked.error) return refusedWith(asked);
  if (await gate.mergesToday(now()) >= merge.MERGES_PER_DAY) {
    return refusedWith({ status: 429, cap: 'merge_day', error: `Today's cap of ${merge.MERGES_PER_DAY} merges is already reached.` });
  }
  const review = await gate.reviewFor({ pr: asked.pr, sha: asked.head_sha });
  if (review.verdict !== 'approve') {
    return refusedWith({ status: 409, refused: review.verdict === 'reject' ? 'review_rejected' : 'review_missing',
      error: review.verdict === 'reject' ? 'The automated review rejected that commit.' : 'No approve is recorded for that commit.' });
  }
  const vet = await merge.vetMerge({ ...account, number: asked.pr, headSha: asked.head_sha, fetcher });
  if (vet.error) return refusedWith(vet);
  const hold = await gate.mergeReserve({ pr: asked.pr, sha: asked.head_sha, at: now() });
  if (!hold.ok) return refusedWith(hold);
  const result = await merge.squashMerge({ ...account, number: asked.pr, headSha: asked.head_sha, title: vet.title, ci: vet.ci, fetcher });
  const outcome = result.merged === true ? 'merged' : result.merged === false ? 'refused' : 'unknown';
  try {
    await gate.mergeSettle({ day: hold.day, id: hold.id, outcome, merge_sha: result.sha ?? null, at: now() });
  } catch {
    // The place stays taken; the record of what became of it is the only thing lost.
  }
  if (result.merged !== true) return refusedWith({ ...result, refused: result.merged === null ? 'no_answer' : result.refused || 'github' },
    { merged: result.merged === null ? 'unknown' : false });
  return json({ ok: true, merged: true, pr: asked.pr, head_sha: asked.head_sha, sha: result.sha, ci: vet.ci, merges_today: hold.count });
}
