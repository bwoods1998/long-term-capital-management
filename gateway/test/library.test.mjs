// The research library (`GET /v1/research/*`, lib/library.mjs): the date rule, the allowlist, the query, the cache, the
// pace, the day's budget, and that no answer ever names a date on or after the cutoff. Every upstream here is a
// stand-in answering from SYNTHETIC fixtures (test/library-fixtures.mjs); the clock and the sleeps are fake, so the pace
// is measured in the fake clock's milliseconds. The suite touches no network.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as L from '../lib/library.mjs';
import { PAPERS, entryXml, feed, errorFeed, article, page, COMMENT_EMAIL } from './library-fixtures.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-09-29T16:00:00Z');
const GATEWAY = 'https://ltcm-gateway.bw.workers.dev';
const BASE_ENV = { GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner' };
const CASES = JSON.parse(readFileSync(new URL('./library-date-cases.json', import.meta.url), 'utf8'));
//: Every URL any test's upstream was asked for: the last test checks each against the allowlist.
const EVERY_URL = [];
//: Every answer body any test read: the last tests check none names a post-cutoff date or the comment's address.
const EVERY_ANSWER = [];

/** A KV namespace in memory with expiry on the harness's clock (`get(key, 'json')`, `put(key, value, {expirationTtl})`). */
function memoryKv(now) {
  const map = new Map();
  return {
    map,
    writes: 0,
    async get(key, type) {
      const row = map.get(key);
      if (!row || row.expires <= now()) return null;
      return type === 'json' ? JSON.parse(row.value) : row.value;
    },
    async put(key, value, options = {}) {
      this.writes += 1;
      map.set(key, { value, expires: now() + (options.expirationTtl ?? 1e9) * 1000 });
    },
  };
}

const atom = (body, status = 200, headers = {}) => new Response(body, { status, headers: { 'Content-Type': 'application/atom+xml; charset=utf-8', ...headers } });
const html = (body, status = 200) => new Response(body, { status, headers: { 'Content-Type': 'text/html; charset=utf-8' } });

/**
 * arXiv as the tests see it, answering from `papers`: a search answers `hits` (bases, their LATEST versions, in rank
 * order); `id_list` answers each id asked (an unversioned id its latest version; an unknown one nothing); arxiv.org/html
 * answers `pages[<base>v<N>]` (else 404); ar5iv answers `ar5iv[<base>]` (else 404). `override(url)` may answer first.
 */
function arxiv({ papers = PAPERS, hits = [], pages = {}, ar5iv = {}, override = null } = {}) {
  return url => {
    const early = override?.(url);
    if (early) return early;
    const parsed = new URL(url);
    if (parsed.hostname === L.API_HOST) {
      const ids = parsed.searchParams.get('id_list');
      if (ids) {
        const entries = [];
        for (const id of ids.split(',')) {
          const match = /^(.+?)(?:v(\d+))?$/.exec(id);
          const paper = papers[match[1]];
          if (!paper) continue;
          const n = match[2] ? Number(match[2]) : paper.versions.length;
          if (n <= paper.versions.length) entries.push(entryXml(match[1], n, paper));
        }
        return atom(feed(entries.reverse()));  // in no fixed order, as the API
      }
      return atom(feed(hits.map(base => entryXml(base, papers[base].versions.length, papers[base]))));
    }
    if (parsed.hostname === L.HTML_HOST) {
      const key = parsed.pathname.replace(/^\/html\//, '').replace(/\/$/, '');
      const found = pages[key];
      return typeof found === 'string' ? html(found) : found instanceof Response ? found : html('Not found', typeof found === 'number' ? found : 404);
    }
    if (parsed.hostname === L.AR5IV_HOST) {
      const key = parsed.pathname.replace(/^\/html\//, '').replace(/\/$/, '');
      const found = ar5iv[key];
      return typeof found === 'string' ? html(found) : html('Not found', typeof found === 'number' ? found : 404);
    }
    return html('unexpected host', 599);
  };
}

/**
 * The route, a gate and a KV on one fake clock. `upstream` answers every fetch (`arxiv(...)`); `calls` records each with
 * the fake time it started; `peak()` is the most fetches in flight at once. The sleeps advance the clock.
 */
function harness({ upstream = arxiv(), env = {}, kv = true, start = NOW } = {}) {
  let t = start;
  const now = () => t;
  const advance = ms => { t += ms; };
  const store = memoryStore();
  const fullEnv = { ...BASE_ENV, ...env, ...(kv ? { LIBRARY: memoryKv(now) } : {}) };
  const gate = createGate({ store, env: fullEnv, now });
  const calls = [];
  let active = 0;
  let most = 0;
  const fetcher = async (url, init = {}) => {
    active += 1;
    most = Math.max(most, active);
    calls.push({ url: String(url), at: t, init });
    EVERY_URL.push(String(url));
    try {
      await Promise.resolve();
      await Promise.resolve();
      const reply = upstream(String(url), init);
      if (reply instanceof Error) throw reply;
      return reply;
    } finally {
      active -= 1;
    }
  };
  // A sleeper wakes at its own time: the clock moves to the latest wake-up, never by the sum of every sleeper's wait.
  const sleep = async ms => {
    const wake = t + ms;
    await Promise.resolve();
    t = Math.max(t, wake);
    await Promise.resolve();
  };
  const get = async (path, params = {}, { token = TOKEN, method = 'GET' } = {}) => {
    const query = new URLSearchParams(params).toString();
    const request = new Request(`${GATEWAY}${path}${query ? `?${query}` : ''}`, {
      method, headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const response = await route(request, fullEnv, { gate, fetcher, now, sleep });
    const body = await response.clone().json().catch(() => null);
    if (path === L.PATHS.search || path === L.PATHS.read) EVERY_ANSWER.push(JSON.stringify(body));
    return { response, body, status: response.status, cache: response.headers.get(L.CACHE_HEADER) };
  };
  const search = (q, extra = {}) => get(L.PATHS.search, { q, ...extra });
  const read = (id, extra = {}) => get(L.PATHS.read, { id, ...extra });
  return { get, search, read, calls, gate, store, env: fullEnv, kv: fullEnv.LIBRARY, now, advance, peak: () => most };
}

const apiCalls = calls => calls.filter(c => new URL(c.url).hostname === L.API_HOST);
const idList = call => new URL(call.url).searchParams.get('id_list');
const searchQuery = call => new URL(call.url).searchParams.get('search_query');

// --- 1. the date rule --------------------------------------------------------------------------------------------------

test('a paper posted in 2025 is refused, a pre-2025 v1-only paper is served, and the boundary second is the rule', async () => {
  const h = harness({ upstream: arxiv({ hits: ['2502.00001', '1602.00865', '2412.09999', '2411.07777'] }) });
  const { status, body } = await h.search('variance risk premium');
  assert.equal(status, 200);
  assert.deepEqual(body.items.map(i => i.id), ['arXiv:1602.00865v1', 'arXiv:2412.09999v1']);
  assert.equal(body.withheld.after_cutoff, 2, 'the 2025 paper, and the 2411 id first posted 2025-01-03');
  const [first, last] = body.items;
  assert.deepEqual(Object.keys(first), ['id', 'title', 'authors', 'first_posted', 'version', 'version_date', 'primary_category',
    'categories', 'abstract', 'url']);
  assert.equal(first.first_posted, '2016-02-02');
  assert.equal(first.url, 'https://arxiv.org/abs/1602.00865v1');
  assert.equal(last.version_date, '2024-12-31', '23:59:59 on the last day is before the cutoff');
  assert.equal(body.last_day, '2024-12-31');
});

test('a paper revised after 2024 is served as it stood at the end of 2024 (its newest earlier version), from ONE batched call', async () => {
  const h = harness({ upstream: arxiv({ hits: ['2207.00949', '2212.06888', '1602.00865'] }) });
  const { body } = await h.search('variance risk premium');
  const api = apiCalls(h.calls);
  assert.equal(api.length, 2, 'the search, then one id_list call for the versions below every revised entry\'s latest');
  assert.deepEqual(idList(api[1]).split(',').sort(), ['2207.00949v1', '2212.06888v1', '2212.06888v2']);
  assert.equal(new URL(api[1].url).searchParams.get('max_results'), '3');
  assert.deepEqual(body.items.map(i => i.id), ['arXiv:2207.00949v1', 'arXiv:2212.06888v2', 'arXiv:1602.00865v1'], 'arXiv\'s rank kept');
  const [v1, v2] = body.items;
  assert.equal(v1.version_date, '2022-07-03', 'v1\'s own date');
  assert.match(v1.abstract, /opportunities in market index options/, 'v1\'s own abstract, not the revised one');
  assert.equal(v2.version_date, '2024-07-01', 'the 2024 revision, not v1 and not the 2026 one');
  assert.match(v2.abstract, /with new data/);
  assert.doesNotMatch(JSON.stringify(body.items), /out-of-sample|2025|2026/);
  assert.equal(body.withheld.revised_earlier, 2);
  // The newest version before the cutoff never changes: it is kept, and the next search of another query asks nothing for it.
  assert.equal(JSON.parse(h.kv.map.get('e:2212.06888').value).version, 2);
  const again = await h.search('perpetual futures variance');
  assert.equal(apiCalls(h.calls).length, 3, 'only the search itself: the revised papers\' versions came from the cache');
  assert.equal(again.body.items.find(i => i.id.startsWith('arXiv:2212.06888')).id, 'arXiv:2212.06888v2');
});

test('a revised paper\'s served version must hold EVERY query term itself (plurals folded)', async () => {
  const h = harness({ upstream: arxiv({ hits: ['2101.00002', '2103.00005', '1602.00865'] }) });
  const { body } = await h.search('variance risk premium');
  assert.deepEqual(body.items.map(i => i.id), ['arXiv:1602.00865v1']);
  assert.equal(body.withheld.revised_unmatched, 2, 'no word of the query (2101), and one word of three (2103): both dropped');
  const entry = { title: 'Index options', summary: 'Volatilities of the dealers\u2019 books; zero-DTE flows.' };
  assert.equal(L.matchesTerms(entry, ['index option', 'volatility', 'dealers', 'zero dte', 'flow']), true, 'plurals and apostrophes folded');
  assert.equal(L.matchesTerms(entry, ['index option', 'skew']), false, 'every term, not one');
  assert.equal(L.matchesTerms(entry, ['option index']), false, 'a phrase in its own order');
  assert.equal(L.matchesTerms(entry, []), false);
  assert.deepEqual(['options', 'volatilities', 'indexes', 'analysis', 'gross', 'bonus', 'prices'].map(L.fold),
    ['option', 'volatility', 'index', 'analysis', 'gross', 'bonus', 'price']);
});

test('a missing or unparseable date, dates that disagree, and a 2501 id claiming 2024 are refused as unreliable', async () => {
  const broken = (base, fields) => ({ base, fields });
  const cases = [
    broken('1602.00865', { published: '' }),
    broken('1602.00865', { updated: 'yesterday' }),
    broken('1602.00865', { published: '2016-02-30T10:00:00Z' }),
    broken('1602.00865', { published: '2016-02-02T10:27:14Z', updated: '2016-01-01T00:00:00Z' }),
    broken('2501.00001', {}),
  ];
  for (const { base, fields } of cases) {
    const upstream = url => (new URL(url).searchParams.get('search_query') ? atom(feed([entryXml(base, 1, PAPERS[base], fields)])) : atom(feed([])));
    const h = harness({ upstream });
    const { body } = await h.search('variance risk premium');
    assert.deepEqual(body.items, [], JSON.stringify(fields));
    assert.equal(body.withheld.no_date, 1, JSON.stringify(fields));
  }
  assert.equal(L.judge({ base: '2501.00001', version: 1, published: '2024-12-30T12:00:00Z', updated: '2024-12-30T12:00:00Z' }), 'no_reliable_date');
  assert.equal(L.judge({ base: '2412.00001', version: 1, published: '2025-01-01T00:00:00Z', updated: '2025-01-01T00:00:00Z' }), 'after_cutoff');
  assert.equal(L.judge({ base: '2412.00001', version: 2, published: '2024-12-01T00:00:00Z', updated: '2025-01-01T00:00:00Z' }), 'revised');
  assert.equal(L.judge({ base: '2412.00001', version: 2, published: '2024-12-01T00:00:00Z', updated: '2024-12-31T23:59:59Z' }), 'ok');
});

test('a read of a version dated after the cutoff is answered exactly as a version that does not exist', async () => {
  const h = harness();
  const late = await h.read('arXiv:2212.06888v3');
  assert.equal(late.status, 404);
  assert.equal(late.body.refused, 'not_found');
  assert.equal(idList(apiCalls(h.calls)[0]).split(',').sort().join(','), '2212.06888,2212.06888v3', 'one call: the latest and the asked');
  const none = await h.read('arXiv:2212.06888v9');
  assert.equal(none.status, late.status);
  assert.deepEqual(Object.keys(none.body).sort(), Object.keys(late.body).sort());
  assert.equal(none.body.refused, late.body.refused);
  assert.equal(none.body.error.replace(' 9 ', ' N '), late.body.error.replace(' 3 ', ' N '), 'the same words, but for the number asked');
  for (const [asked, missing] of [['2207.00949v2', '2207.00949v5'], ['2101.00002v2', '2101.00002v3']]) {
    const [a, b] = [await h.read(asked), await h.read(missing)];
    assert.deepEqual([a.status, a.body.refused], [404, 'not_found'], asked);
    assert.deepEqual([b.status, b.body.refused], [404, 'not_found'], missing);
  }
  const early = await h.read('2212.06888v1');
  assert.equal(early.body.id, 'arXiv:2212.06888v1', 'a pre-2025 version named is served as itself');
  const middle = await h.read('2212.06888v2');
  assert.equal(middle.body.id, 'arXiv:2212.06888v2');
  assert.equal(middle.body.served_earlier_version, false);
});

test('an unversioned read serves the paper as it stood at the end of 2024: its newest version before the cutoff', async () => {
  const h = harness();
  const plain = await h.read('2212.06888');
  assert.equal(plain.body.id, 'arXiv:2212.06888v2', 'v3 is 2026, v2 is 2024: v2, not v1');
  assert.equal(plain.body.version_date, '2024-07-01');
  assert.equal(plain.body.served_earlier_version, true);
  const api = apiCalls(h.calls);
  assert.equal(api.length, 2, 'the latest and v1, then the versions between');
  assert.equal(idList(api[0]).split(',').sort().join(','), '2212.06888,2212.06888v1');
  assert.equal(idList(api[1]), '2212.06888v2');
  const again = await h.read('arXiv:2212.06888');
  assert.equal(again.body.id, 'arXiv:2212.06888v2');
  assert.equal(apiCalls(h.calls).length, 2, 'from the cache (e: and m:)');
  const once = harness();
  assert.equal((await once.read('2207.00949')).body.id, 'arXiv:2207.00949v1', 'two versions: v1, in ONE call');
  assert.equal(apiCalls(once.calls).length, 1);
  assert.equal((await once.read('1805.01234')).body.id, 'arXiv:1805.01234v2', 'every version pre-2025: the latest');
  // A search and a read show a paper as the same version, so neither says whether it was revised after 2024.
  const both = harness({ upstream: arxiv({ hits: ['2212.06888', '2207.00949', '1805.01234'] }) });
  const found = (await both.search('variance risk premium', { max: '10' })).body.items;
  assert.equal(found.length, 3);
  for (const item of found) {
    const base = item.id.replace(/^arXiv:/, '').replace(/v[0-9]+$/, '');
    assert.equal((await both.read(base)).body.id, item.id, base);
  }
});

test('a read of a paper posted after the cutoff is a 403 and names nothing of it', async () => {
  const h = harness();
  for (const id of ['2502.00001', '2502.00001v1', '2411.07777', 'arXiv:2601.00001v2']) {
    const { status, body } = await h.read(id);
    assert.equal(status, 403, id);
    assert.equal(body.refused, 'after_cutoff', id);
    assert.equal(Object.keys(body).sort().join(','), 'error,refused');
  }
  assert.equal(apiCalls(h.calls).length, 1, 'a 25xx or 26xx id is refused by its name, without asking arXiv');
});

test('off-topic items are withheld; cs.LG only where it concerns markets', async () => {
  const h = harness({ upstream: arxiv({ hits: ['2001.00003', '2305.18991', '2305.00004'] }) });
  const { body } = await h.search('variance risk premium');
  assert.deepEqual(body.items.map(i => i.id), ['arXiv:2305.18991v1']);
  assert.equal(body.withheld.off_topic, 2);
  const read = await h.read('2001.00003');
  assert.equal(read.status, 403);
  assert.equal(read.body.refused, 'off_topic');
});

// --- 2. the allowlist --------------------------------------------------------------------------------------------------

test('the allowlist admits exactly three shapes and refuses every look-alike', () => {
  const admitted = [
    'https://export.arxiv.org/api/query?search_query=all%3Avol',
    'https://arxiv.org/html/2409.06496v1',
    'https://arxiv.org/html/2409.06496v12/',
    'https://ar5iv.labs.arxiv.org/html/1805.01234',
    'https://ar5iv.labs.arxiv.org/html/cond-mat/0601001',
  ];
  for (const url of admitted) assert.equal(L.checkLibraryUrl(url).ok, true, url);
  const refused = [
    'http://export.arxiv.org/api/query?id_list=1',
    'https://export.arxiv.org:8443/api/query?id_list=1',
    'https://user:pw@export.arxiv.org/api/query?id_list=1',
    'https://export.arxiv.org/api/query',
    'https://export.arxiv.org/oai2?verb=Identify',
    'https://export.arxiv.org.evil.com/api/query?x=1',
    'https://export.arxiv.org@evil.com/api/query?x=1',
    'https://arxiv.org/html/2409.06496',
    'https://arxiv.org/pdf/2409.06496v1',
    'https://arxiv.org/abs/2409.06496v1',
    'https://arxiv.org/e-print/2409.06496v1',
    'https://arxiv.org/src/2409.06496v1',
    'https://arxiv.org/html/2409.06496v1?download=1',
    'https://arxiv.org./html/2409.06496v1',
    'https://www.arxiv.org/html/2409.06496v1',
    'https://ar5iv.org/html/1805.01234',
    'https://ar5iv.labs.arxiv.org/log/1805.01234',
    'https://ar5iv.labs.arxiv.org/html/1805.01234#S1',
    'https://151.101.1.42/api/query?x=1',
    'https://[2a04:4e42::347]/api/query?x=1',
    'https://аrxiv.org/html/2409.06496v1',
    'https://arxiv.org/html/../pdf/2409.06496v1',
    'ftp://arxiv.org/html/2409.06496v1',
    'not a url',
  ];
  for (const url of refused) assert.equal(L.checkLibraryUrl(url).ok, false, url);
});

test('a redirect to another host, or to arxiv.org/html without its version, is refused and fetched no further', async () => {
  for (const location of ['https://evil.example/html/2409.06496v1', 'https://arxiv.org/html/2409.06496', 'https://arxiv.org/pdf/2409.06496v1']) {
    const upstream = arxiv({ override: url => (new URL(url).hostname === L.HTML_HOST
      ? new Response(null, { status: 301, headers: { Location: location } }) : null) });
    const h = harness({ upstream });
    const { status, body } = await h.read('2409.06496');
    assert.equal(status, 200);
    assert.equal(body.text_source, 'none');
    assert.equal(h.calls.filter(c => !L.checkLibraryUrl(c.url).ok).length, 0, location);
    assert.equal(h.calls.some(c => c.url === location), false, location);
  }
});

test('a redirect inside the allowlist is followed as another paced request', async () => {
  const upstream = arxiv({
    pages: { '2409.06496v1': page(article()) },
    override: url => (url === 'https://arxiv.org/html/2409.06496v1' ? new Response(null, { status: 301, headers: { Location: '/html/2409.06496v1/' } }) : null),
  });
  const h = harness({ upstream });
  const { body } = await h.read('2409.06496');
  assert.equal(body.text_source, 'arxiv_html');
  const hops = h.calls.filter(c => new URL(c.url).hostname === L.HTML_HOST);
  assert.equal(hops.length, 2);
  assert.ok(hops[1].at - hops[0].at >= L.SPACING_MS[L.HTML_HOST], 'the hop waited its turn');
});

test('no page of a new-style id after 2412 is on the allowlist', () => {
  for (const url of ['https://arxiv.org/html/2501.00001v1', 'https://arxiv.org/html/2609.12345v2/', 'https://ar5iv.labs.arxiv.org/html/2503.01234',
    'https://ar5iv.labs.arxiv.org/html/2503.01234v1', 'https://arxiv.org/html/2413.00001v1']) {
    assert.equal(L.checkLibraryUrl(url).ok, false, url);
  }
  for (const url of ['https://arxiv.org/html/2412.09999v1', 'https://ar5iv.labs.arxiv.org/html/2412.09999']) assert.equal(L.checkLibraryUrl(url).ok, true, url);
});

test('a redirect to another version, another paper or another query is refused and never fetched', async () => {
  // The reviewer's probe: /html/<id>v1 redirected to v2 served the 2026 version's text under the 2024 v1's id.
  const pages = { '2408.03333v2': page(article({ lead: 'The re-estimated version, with the 2026 sample.' })) };
  for (const location of ['/html/2408.03333v2', 'https://arxiv.org/html/2408.03333v2/', 'https://arxiv.org/html/2409.06496v1',
    'https://arxiv.org/html/2503.01234v1', 'https://ar5iv.labs.arxiv.org/html/2408.03333']) {
    const upstream = arxiv({ pages, override: url => (url === 'https://arxiv.org/html/2408.03333v1'
      ? new Response(null, { status: 302, headers: { Location: location } }) : null) });
    const h = harness({ upstream });
    const { status, body } = await h.read('2408.03333v1');
    assert.equal(status, 200, location);
    assert.equal(body.id, 'arXiv:2408.03333v1');
    assert.equal(body.text_source, 'none', location);
    assert.equal(body.text, '');
    assert.equal(h.calls.filter(c => new URL(c.url).hostname === L.HTML_HOST).length, 1, `only v1's own page was asked (${location})`);
    assert.equal(h.calls.some(c => c.url.includes('2408.03333v2') || c.url.includes('2409.06496') || c.url.includes('2503.')), false, location);
    assert.equal([...h.kv.map.keys()].includes('t0:2408.03333v1'), false, 'a refused redirect is not a lasting "no text"');
  }
  // An API answer that redirects to another question is refused, never asked.
  const moved = harness({ upstream: arxiv({ hits: ['1602.00865'], override: url => (new URL(url).searchParams.get('search_query')?.includes('tail')
    ? new Response(null, { status: 301, headers: { Location: 'https://export.arxiv.org/api/query?search_query=all%3Atail&max_results=10' } }) : null) }) });
  const refused = await moved.search('tail risk');
  assert.equal(refused.status, 500);
  assert.equal(moved.calls.length, 1);
  // ar5iv may name the paper's version, but not one past its confirmed latest.
  assert.equal(L.sameAr5iv('1805.01234', 2)(new URL('https://ar5iv.labs.arxiv.org/html/1805.01234v2')), true);
  assert.equal(L.sameAr5iv('1805.01234', 2)(new URL('https://ar5iv.labs.arxiv.org/html/1805.01234/')), true);
  assert.equal(L.sameAr5iv('1805.01234', 2)(new URL('https://ar5iv.labs.arxiv.org/html/1805.01234v3')), false);
  assert.equal(L.sameAr5iv('1805.01234', 2)(new URL('https://ar5iv.labs.arxiv.org/html/1805.012345')), false);
  assert.equal(L.samePage('cond-mat/0601001', 1)(new URL('https://arxiv.org/html/cond-mat/0601001v1/')), true);
  assert.equal(L.samePage('cond-mat/0601001', 1)(new URL('https://arxiv.org/html/cond-mat/0601001v2')), false);
  const later = harness({ upstream: arxiv({ ar5iv: { '1805.01234v3': page(article()) }, override: url => (url === 'https://ar5iv.labs.arxiv.org/html/1805.01234'
    ? new Response(null, { status: 301, headers: { Location: '/html/1805.01234v3' } }) : null) }) });
  const past = await later.read('1805.01234');
  assert.equal(past.body.text_source, 'none', 'a version past the confirmed latest (v2)');
  assert.equal(later.calls.some(c => c.url.endsWith('1805.01234v3')), false);
});

test('only a fixed User-Agent and Accept leave, and no credential', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  await h.search('tail risk');
  for (const call of h.calls) {
    assert.deepEqual(Object.keys(call.init.headers).sort(), ['Accept', 'User-Agent']);
    assert.equal(call.init.headers['User-Agent'], L.USER_AGENT);
    assert.equal(call.init.redirect, 'manual');
    assert.equal(call.init.method, 'GET');
  }
});

// --- 3. the query ------------------------------------------------------------------------------------------------------

test('the gateway builds every query: injection, field syntax and years from 2025 on are stripped; the date clause always ends it', () => {
  const cases = {
    'x AND submittedDate:[202501010000 TO 202612312359]': ['submitteddate'],
    'vol lastUpdatedDate:[2025 TO 2026] (ti:foo) OR au:bar': ['vol', 'lastupdateddate', 'ti', 'foo', 'au', 'bar'],
    'variance risk premium 2025 2026 fy2025 of the': ['variance', 'risk', 'premium'],
    '"variance risk premium" index options': ['variance risk premium', 'index', 'options'],
    'zero-dte dealer\'s gamma': ['zero dte', 'dealers', 'gamma'],
    'ANDNOT spam and eggs or ham': ['spam', 'eggs', 'ham'],
    'a b c d e f g h i j k l': [],
    'one two three four five six seven eight nine ten': ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight'],
    '"unclosed phrase here': ['unclosed', 'phrase', 'here'],
  };
  for (const [q, terms] of Object.entries(cases)) {
    const built = L.buildQuery(q, 'all');
    if (!terms.length) {
      assert.ok(built.error, q);
      continue;
    }
    assert.deepEqual(built.terms, terms, q);
    assert.ok(built.query.endsWith(` AND ${L.DATE_CLAUSE}`), q);
    assert.equal((built.query.match(/submittedDate/g) || []).length, 1, `${q}: one date clause, the gateway's`);
    // Every term is plain words, and the only field syntax is the gateway's own: each term in a title or an abstract.
    for (const term of built.terms) assert.match(term, /^[a-z0-9]+(?: [a-z0-9]+)*$/, q);
    const clauses = built.terms.map(L.inTitleOrAbstract).join(' AND ');
    assert.ok(built.query.includes(` AND (${clauses}) AND `), q);
    const body = built.query.slice(0, -L.DATE_CLAUSE.length).replace(clauses, '');
    assert.doesNotMatch(body, /\[|\]|lastUpdatedDate|au:|all:|202[5-9]/, q);
  }
  assert.equal(L.inTitleOrAbstract('vol'), '(ti:vol OR abs:vol)');
  assert.equal(L.inTitleOrAbstract('variance risk premium'), '(ti:"variance risk premium" OR abs:"variance risk premium")');
  assert.deepEqual(L.buildQuery('fy2025 test 2048').terms, ['test'], 'a word holding a year from 2025 on is dropped whole');
  assert.deepEqual(L.buildQuery('returns in 2019').terms, ['returns', '2019'], 'an earlier year is a word');
  assert.equal(L.buildQuery('2025 2026').error.includes('no searchable words'), true);
  assert.ok(L.buildQuery('x', 'all').error);
  assert.ok(L.buildQuery('y'.repeat(201)).error);
  assert.ok(L.buildQuery('vol', 'physics').error);
});

test('the category clause: all, q-fin, econ, stat.ML, and cs.LG only on markets; titles and abstracts only, never all:', () => {
  assert.match(L.buildQuery('vol', 'q-fin').query, /^cat:q-fin\.\* AND \(\(ti:vol OR abs:vol\)\) AND /);
  assert.match(L.buildQuery('vol', 'econ').query, /^cat:econ\.\* AND /);
  assert.match(L.buildQuery('vol', 'stat.ML').query, /^cat:stat\.ML AND /);
  assert.match(L.buildQuery('vol', 'cs.LG').query, /^\(cat:cs\.LG AND \(ti:market OR abs:market OR .*ti:price OR abs:price\)\) AND /);
  const all = L.buildQuery('vol').query;
  for (const part of ['cat:q-fin.*', 'cat:econ.*', 'cat:stat.ML', '(cat:cs.LG AND (ti:market OR abs:market']) assert.ok(all.includes(part), part);
  assert.ok(all.startsWith('(cat:q-fin.* OR cat:econ.* OR cat:stat.ML OR (cat:cs.LG AND (ti:market OR abs:market OR '));
  // `all:` also searches comments and journal references, which an author can add after 2024 without a new version
  // (verified live Sept 29: `all:"Review of Financial Studies"` found 6 q-fin papers, titles and abstracts 3).
  for (const cat of L.CATEGORIES) assert.doesNotMatch(L.buildQuery('"variance risk premium" skew', cat).query, /all:/, cat);
});

test('the search asks arXiv for twice max, by relevance, and a bad query or max is a 400 that asks nothing', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  await h.search('tail risk', { max: '3', cat: 'q-fin' });
  const params = new URL(h.calls[0].url).searchParams;
  assert.equal(params.get('max_results'), '6');
  assert.equal(params.get('sortBy'), 'relevance');
  assert.equal(searchQuery(h.calls[0]),
    'cat:q-fin.* AND ((ti:tail OR abs:tail) AND (ti:risk OR abs:risk)) AND submittedDate:[199101010000 TO 202412312359]');
  for (const bad of [{ q: '' }, { q: 'x' }, { q: 'tail', max: '0' }, { q: 'tail', max: '11' }, { q: 'tail', max: '2.5' }, { q: 'tail', cat: 'hep-th' }]) {
    const { status, body } = await h.get(L.PATHS.search, bad);
    assert.equal(status, 400, JSON.stringify(bad));
    assert.equal(body.refused, 'query');
  }
  assert.equal(h.calls.length, 1);
  for (const id of ['', 'hello', '2409.06496v0', '2413.00001', '../2409.06496', '2409.06496v1; DROP']) {
    const { status, body } = await h.read(id);
    assert.equal(status, 400, id);
    assert.equal(body.refused, 'id');
  }
  assert.equal(h.calls.length, 1);
});

// --- 4. caching --------------------------------------------------------------------------------------------------------

test('a second identical search is answered from the cache with no upstream call', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865', '2207.00949'] }) });
  const first = await h.search('variance risk premium');
  assert.equal(first.cache, 'miss');
  assert.equal(first.body.cached, false);
  const before = h.calls.length;
  h.advance(3600_000);
  const second = await h.search('  "variance"   risk premium ');
  assert.equal(h.calls.length, before, 'the same terms: no call');
  assert.equal(second.cache, 'hit');
  assert.equal(second.body.cached, true);
  assert.deepEqual(second.body.items, first.body.items);
  assert.equal(h.gate.libraryStatus().upstream, 2);
});

test('a search answer cached before the review\'s fixes (v: 1) is never read again', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  const digest = async value => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))]
    .map(b => b.toString(16).padStart(2, '0')).join('');
  const old = `s:${await digest(JSON.stringify({ v: 1, terms: ['tail', 'risk'], cat: 'all', max: 5 }))}`;
  const planted = { items: [{ ...L.admitItem({ id: 'arXiv:2207.00949v1', title: 'Stochastic arbitrage', authors: ['Fay Ionescu'],
    first_posted: '2022-07-03', version: 1, version_date: '2022-07-03', primary_category: 'q-fin.PM', categories: ['q-fin.PM'],
    abstract: 'Found through a word only its 2025 revision holds.', url: 'https://arxiv.org/abs/2207.00949v1' }) }] };
  await h.kv.put(old, JSON.stringify(planted), { expirationTtl: 86400 });
  const { body, cache } = await h.search('tail risk');
  assert.equal(cache, 'miss');
  assert.deepEqual(body.items.map(i => i.id), ['arXiv:1602.00865v1']);
});

test('a cached item with a post-cutoff date is never served: the search goes upstream again', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  await h.search('tail risk');
  const [key] = [...h.kv.map.keys()].filter(k => k.startsWith('s:'));
  const row = JSON.parse(h.kv.map.get(key).value);
  row.items[0].version_date = '2025-03-01';
  h.kv.map.set(key, { value: JSON.stringify(row), expires: Infinity });
  const again = await h.search('tail risk');
  assert.equal(again.cache, 'miss');
  assert.equal(again.body.items[0].version_date, '2016-02-02');
  for (const planted of [{ ...row.items[0], version_date: '2016-02-02', abstract: 'by December 2025' }, { ...row.items[0], id: 'arXiv:2501.00001v1' }]) {
    assert.equal(L.admitItem(planted), null);
  }
});

test('a cache entry expires and is fetched again; no text is remembered for a week', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  await h.search('tail risk');
  h.advance(L.TTL.search * 1000 + 1);
  const again = await h.search('tail risk');
  assert.equal(again.cache, 'miss');
  const r1 = await h.read('1602.00865');
  assert.equal(r1.body.text_source, 'none');
  const calls = h.calls.length;
  const r2 = await h.read('1602.00865');
  assert.equal(h.calls.length, calls, 'metadata and "no text" both cached');
  assert.equal(r2.cache, 'hit');
  assert.ok([...h.kv.map.keys()].includes('t0:1602.00865v1'));
});

test('without the KV binding the library answers uncached, still paced and counted', async () => {
  const h = harness({ kv: false, upstream: arxiv({ hits: ['1602.00865'] }) });
  const first = await h.search('tail risk');
  const second = await h.search('tail risk');
  assert.equal(first.status, 200);
  assert.equal(second.cache, 'miss');
  assert.equal(h.calls.length, 2);
  assert.ok(h.calls[1].at - h.calls[0].at >= 3000);
  assert.equal(h.gate.libraryStatus().upstream, 2);
});

test('a read\'s text is cached, the window moves with start, and sections point into the text', async () => {
  const h = harness({ upstream: arxiv({ pages: { '2409.06496v1': page(article({ extra: 'x'.repeat(9000) })) } }) });
  const first = await h.read('2409.06496', { chars: '500' });
  assert.equal(first.body.text_source, 'arxiv_html');
  assert.equal(first.body.text.length, 500);
  assert.equal(first.body.next_start, 500);
  const titles = first.body.sections.map(s => s.title);
  assert.deepEqual(titles, ['1 Introduction', '1.1 Data', '2 Results']);
  const second = await h.read('arXiv:2409.06496v1', { start: String(first.body.sections[2].start), chars: '200' });
  assert.equal(second.cache, 'hit', 'metadata and text from the cache');
  assert.ok(second.body.text.startsWith('2 Results'));
  const tail = await h.read('2409.06496v1', { start: String(first.body.total_chars - 10) });
  assert.equal(tail.body.next_start, null);
  assert.equal(tail.body.text.length, 10);
});

// --- 5. the pace -------------------------------------------------------------------------------------------------------

test('arXiv\'s pace: API requests 3 s apart, arxiv.org 15 s apart, never two in flight', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'], pages: { '2409.06496v1': page(article()), '2412.09999v1': page(article()) } }) });
  await Promise.all([h.search('variance risk premium'), h.search('tail risk'), h.read('2409.06496'), h.read('2412.09999'), h.search('overnight options')]);
  const byHost = host => h.calls.filter(c => new URL(c.url).hostname === host).map(c => c.at);
  for (const [host, gap] of [[L.API_HOST, 3000], [L.HTML_HOST, 15000]]) {
    const starts = byHost(host);
    assert.ok(starts.length >= 2, host);
    for (let i = 1; i < starts.length; i++) assert.ok(starts[i] - starts[i - 1] >= gap, `${host}: ${starts[i] - starts[i - 1]} ms`);
  }
  assert.equal(h.peak(), 1, 'one connection at a time across every host');
  assert.equal(h.gate.libraryStatus().in_flight, null, 'every lease released');
});

test('a wait past the request\'s budget is 429 busy: nothing sent, nothing counted', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  h.store.set('library-v1', JSON.stringify({ day: '2026-09-29', upstream: 3, backoff_until: NOW + 120_000, backoff_why: 'test', last: {} }));
  const { status, body, response } = await h.search('tail risk');
  assert.equal(status, 429);
  assert.equal(body.busy, true);
  assert.ok(Number(response.headers.get('Retry-After')) >= 3);
  assert.equal(h.calls.length, 0);
  assert.equal(h.gate.libraryStatus().upstream, 3);
});

test('arXiv\'s 429 or 503 starts a backoff of its Retry-After (at least 60 s), and the next request waits it out', async () => {
  for (const code of [429, 503]) {
    let first = true;
    const upstream = arxiv({ hits: ['1602.00865'], override: () => {
      if (!first) return null;
      first = false;
      return atom('slow down', code, { 'Retry-After': '120' });
    } });
    const h = harness({ upstream });
    const refused = await h.search('tail risk');
    assert.equal(refused.status, 503, 'arXiv asked us to slow down');
    assert.equal(refused.body.backoff, true);
    const status = h.gate.libraryStatus();
    assert.equal(status.backoff_until, new Date(NOW + 120_000).toISOString());
    const busy = await h.search('tail risk');
    assert.equal(busy.status, 429, 'inside the backoff and past the budget: busy');
    h.advance(100_000);
    const ok = await h.search('tail risk');
    assert.equal(ok.status, 200);
    assert.ok(h.calls[1].at >= NOW + 120_000, 'the second request started after the backoff');
  }
  const h = harness();
  const turn = h.gate.libraryAcquire({ host: L.API_HOST });
  assert.deepEqual(h.gate.libraryRelease({ id: turn.id, status: 503, retry_after_ms: 5_000 }), { ok: true });
  assert.equal(h.gate.libraryStatus().backoff_until, new Date(NOW + L.BACKOFF_MS).toISOString(), 'never less than 60 s');
});

test('no upstream request starts past the request\'s budget, so a library request ends within WORST_MS', async () => {
  let h;
  const upstream = arxiv({ pages: { '2409.06496v1': page(article()) }, override: url => {
    if (new URL(url).hostname === L.API_HOST) h.advance(L.REQUEST_BUDGET_MS + 1);  // arXiv's API answered slowly
    return null;
  } });
  h = harness({ upstream });
  const { status, body } = await h.read('2409.06496');
  assert.equal(status, 200, 'the metadata came back: the item is served');
  assert.equal(body.text_source, 'none');
  assert.match(body.text_note, /busy/);
  assert.equal(h.calls.filter(c => new URL(c.url).hostname === L.HTML_HOST).length, 0, 'the page was not asked for past the budget');
  assert.equal([...h.kv.map.keys()].includes('t0:2409.06496v1'), false, 'and "no text" is not remembered');
  assert.equal(L.WORST_MS, L.REQUEST_BUDGET_MS + Math.max(...Object.values(L.FETCH_TIMEOUT_MS)));
  assert.ok(L.WORST_MS <= 35_000, 'the House\'s client outwaits it (league/swarm/library.py CLIENT_FLOOR_SECONDS)');
  assert.ok(L.IN_FLIGHT_STALE_MS >= L.WORST_MS && L.IN_FLIGHT_STALE_MS <= 60_000);
});

test('a 403 from arXiv starts the backoff as a 429 does, and a 403 or 451 is never remembered as "no text"', async () => {
  let first = true;
  const blocked = harness({ upstream: arxiv({ hits: ['1602.00865'], override: () => {
    if (!first) return null;
    first = false;
    return html('Forbidden', 403);
  } }) });
  const refused = await blocked.search('tail risk');
  assert.equal(refused.status, 503);
  assert.equal(refused.body.backoff, true);
  assert.equal(blocked.gate.libraryStatus().backoff_until, new Date(NOW + L.BACKOFF_MS).toISOString());
  assert.equal((await blocked.search('tail risk')).status, 429, 'inside the backoff: busy, nothing sent');
  assert.equal(blocked.calls.length, 1);
  for (const code of [403, 451]) {
    for (const id of ['2409.06496', '1805.01234']) {
      const h = harness({ upstream: arxiv({ pages: { '2409.06496v1': code }, ar5iv: { '1805.01234': code } }) });
      const { body } = await h.read(id);
      assert.equal(body.text_source, 'none', `${code} ${id}`);
      assert.match(body.text_note, /could not be read/, `${code} ${id}`);
      assert.deepEqual([...h.kv.map.keys()].filter(k => k.startsWith('t0:')), [], `${code} ${id}: nothing remembered`);
      assert.equal(Boolean(h.gate.libraryStatus().backoff_until), code === 403, `${code}: a 403 pauses every host, a 451 does not`);
    }
  }
});

test('a lease no worker released expires at its start plus the timeout plus 5 s', () => {
  const h = harness();
  const turn = h.gate.libraryAcquire({ host: L.API_HOST });
  assert.equal(turn.go, true);
  h.advance(5000);
  const blocked = h.gate.libraryAcquire({ host: L.AR5IV_HOST });
  assert.equal(blocked.go, false, 'one connection at a time, across hosts');
  h.advance(L.FETCH_TIMEOUT_MS[L.API_HOST] + L.LEASE_SLACK_MS - 5000);
  assert.equal(h.gate.libraryAcquire({ host: L.AR5IV_HOST }).go, true, 'the stale lease is gone');
  assert.deepEqual(h.gate.libraryRelease({ id: turn.id }), { ok: false }, 'a late release frees nothing that is not its own');
  assert.equal(h.gate.libraryAcquire({ host: 'example.com' }).refused, 'host');
});

// --- 6. the day's budget -----------------------------------------------------------------------------------------------

test('the day\'s cap: 429 library_day; cache hits still answer; the count rolls at UTC midnight; health reports it', async () => {
  const h = harness({ env: { LIBRARY_DAY_UPSTREAM: '2' }, upstream: arxiv({ hits: ['1602.00865'] }) });
  assert.equal((await h.search('tail risk')).status, 200);
  assert.equal((await h.search('options overnight')).status, 200);
  const capped = await h.search('volatility skew');
  assert.equal(capped.status, 429);
  assert.equal(capped.body.cap, 'library_day');
  assert.equal(h.calls.length, 2);
  const hit = await h.search('tail risk');
  assert.equal(hit.status, 200);
  assert.equal(hit.cache, 'hit', 'a cache hit is free at the cap');
  const health = await h.get('/v1/health');
  assert.equal(health.body.library.upstream, 2);
  assert.equal(health.body.library.cap, 2);
  assert.deepEqual(health.body.library.by_host, { [L.API_HOST]: 2 });
  assert.equal(h.calls.length, 2, '/v1/health asks arXiv nothing');
  const own = await h.get(L.PATHS.health);
  assert.deepEqual(own.body.library, health.body.library);
  h.advance(8 * 3600_000 + 1);  // 16:00Z + 8 h: the next UTC day
  assert.equal((await h.search('volatility skew')).status, 200);
  assert.equal(h.gate.libraryStatus().upstream, 1);
  assert.equal(L.dayCap({}), 600);
  for (const bad of ['-1', 'many', '1.5', '999999']) assert.equal(L.dayCap({ LIBRARY_DAY_UPSTREAM: bad }), 600, bad);
  assert.equal(L.dayCap({ LIBRARY_DAY_UPSTREAM: '0' }), 0, 'zero closes the library');
});

test('the role asking is counted by name in the Gate', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  await h.search('tail risk', { role: 'architect' });
  await h.search('skew', { role: 'Not A Slug!' });
  assert.deepEqual(h.gate.libraryStatus().by_role, { architect: 1, unattributed: 1 });
});

test('a malformed library row never makes /v1/health throw (the House reads a failed health as the kill switch)', async () => {
  const rows = [
    JSON.stringify({ day: '2026-09-29', inflight: { id: 1, host: 'arxiv.org', expires: NOW + 86_400_000 } }),  // a lease without `at`
    JSON.stringify({ day: '2026-09-29', inflight: { id: 1, host: 'arxiv.org', at: 'soon', expires: NOW + 60_000 } }),
    JSON.stringify({ day: '2026-09-29', backoff_until: 1e300 }),
    'null', '[]', '7', '"text"', '{not json',
  ];
  for (const row of rows) {
    const h = harness();
    h.store.set('library-v1', row);
    const status = h.gate.status();
    assert.equal(status.ok, true, row);
    assert.equal(typeof status.library, 'object', row);
    const health = await h.get('/v1/health');
    assert.equal(health.status, 200, row);
    assert.equal(health.body.kill_switch, false, row);
    const own = await h.get(L.PATHS.health);
    assert.ok([200, 503].includes(own.status), row);
    h.gate.libraryRelease({ id: 1, status: 200 });  // a release over a malformed row does not throw either
  }
  const h = harness();
  h.gate.libraryStatus = () => { throw new RangeError('Invalid time value'); };
  const health = await h.get('/v1/health');
  assert.equal(health.status, 200, 'a library fault is the block\'s own answer, never /v1/health\'s');
  assert.deepEqual(health.body.library, { error: 'library status unreadable' });
  assert.equal((await h.get(L.PATHS.health)).status, 503);
});

// --- 7. no post-2024 date in any output ----------------------------------------------------------------------------------

test('the date scan: every case in the shared list', () => {
  for (const text of CASES.match) {
    assert.equal(L.hasPostCutoff(text), true, text);
    const clean = L.scrubDates(text);
    assert.equal(L.hasPostCutoff(clean), false, `${text} -> ${clean}`);
  }
  for (const text of CASES.clean) {
    assert.equal(L.hasPostCutoff(text), false, text);
    assert.equal(L.scrubDates(text), text, text);
  }
});

test('a forecast in a pinned abstract becomes [date]; the item is served', async () => {
  const h = harness({ upstream: arxiv({ hits: ['2311.04444', '2412.09999'] }) });
  const { body } = await h.search('variance risk premium');
  const [bond, late] = body.items;
  assert.equal(bond.abstract, 'Notes maturing on [date] carry a variance risk premium by [date], by our estimate.');
  assert.match(late.abstract, /forecasts to \[date\] are given/);
});

test('arXiv\'s page chrome is outside the article; a date inside pinned HTML is replaced', async () => {
  const pages = { '2409.06496v1': page(article({ extra: 'The notes mature on 2026-12-14.' })) };
  const h = harness({ upstream: arxiv({ pages }) });
  const { body } = await h.read('2409.06496');
  assert.equal(body.text_source, 'arxiv_html');
  assert.doesNotMatch(body.text, /Fonticons|Copyright|September 2026|Generated on|arxiv-html-papers/);
  assert.match(body.text, /mature on \[date\]/);
  assert.match(body.text, /\\sigma\^\{2\}_\{t\}-\\mathbb\{E\}\[RV\]/, 'a formula reads as its TeX');
  assert.doesNotMatch(body.text, /σ/, 'not as its glyphs');
  assert.match(body.text, /pp\. 2037–2053/, 'page numbers are no date');
  assert.match(body.text, /Contact: \[email\]\./, 'an author\'s address is redacted');
  assert.doesNotMatch(body.text, /@/);
});

test('ar5iv only for a paper whose every version is pre-2025, and withheld whole when it names a later date', async () => {
  const ar5iv = {
    '1805.01234': page(article({ lead: 'Overnight returns. First draft May 2018. This draft February 2019.' })),
    '1901.05555': page(article({ lead: 'Momentum. First draft January 2019. This draft March 2025.' })),
    '2212.06888': page(article({ lead: 'Perpetuals. This draft July 2024.' })),
  };
  const h = harness({ upstream: arxiv({ ar5iv }) });
  const ok = await h.read('1805.01234');
  assert.equal(ok.body.text_source, 'ar5iv');
  assert.match(ok.body.text, /This draft February 2019/);
  const withheld = await h.read('1901.05555');
  assert.equal(withheld.body.text_source, 'none');
  assert.equal(withheld.body.text, '');
  const revised = await h.read('2212.06888');
  assert.equal(revised.body.id, 'arXiv:2212.06888v2');
  assert.equal(revised.body.text_source, 'none', 'its latest is 2026: ar5iv is never asked');
  assert.equal(h.calls.some(c => c.url.endsWith('/html/2212.06888')), false);
  const older = await h.read('1805.01234v1');
  assert.equal(older.body.id, 'arXiv:1805.01234v1');
  assert.equal(older.body.text_source, 'none', 'ar5iv renders the latest: never served as an older version');
});

test('ar5iv is read only after the paper\'s latest version was confirmed within the hour', async () => {
  const h = harness({ upstream: arxiv({ ar5iv: { '1805.01234': page(article()) } }) });
  await h.read('1805.01234v2', { chars: '10' });
  const [key] = [...h.kv.map.keys()].filter(k => k.startsWith('t:'));
  h.kv.map.delete(key);  // the text forgotten, the metadata still cached
  h.advance(2 * 3600_000);
  const before = apiCalls(h.calls).length;
  const again = await h.read('1805.01234v2');
  assert.equal(again.body.text_source, 'ar5iv');
  assert.equal(apiCalls(h.calls).length, before + 1, 'the latest version asked again before ar5iv');
});

test('no answer names a post-cutoff date, nor the comment\'s address, nor a journal reference', async () => {
  const bases = Object.keys(PAPERS);
  const pages = { '2409.06496v1': page(article({ extra: 'Through 2030 and by Q3 2027.' })) };
  const ar5iv = { '1805.01234': page(article()), 'cond-mat/0601001': page(article({ lead: 'Tails.' })) };
  const h = harness({ upstream: arxiv({ hits: bases, pages, ar5iv }) });
  const answers = [(await h.search('variance risk premium', { max: '10' })).body];
  for (const base of bases) {
    for (const suffix of ['', 'v1', 'v2', 'v3']) {
      const { body, status } = await h.read(base + suffix);
      answers.push(body);
      if (status === 200) assert.ok(body.version_date < '2025-01-01' && body.first_posted < '2025-01-01');
    }
  }
  for (const body of answers) {
    const text = JSON.stringify(body);
    assert.equal(L.hasPostCutoff(text), false, text.slice(0, 300));
    assert.doesNotMatch(text, new RegExp(COMMENT_EMAIL.replace('.', '\\.')));
    assert.doesNotMatch(text, /Invented Results|arxiv:comment|journal_ref/);
  }
  const old = answers.find(b => b && b.id === 'arXiv:cond-mat/0601001v1');
  assert.equal(old.text_source, 'ar5iv', 'an old-style id is read too');
  assert.equal(old.abstract, 'Heavy tails of option returns & their pricing.', 'entities decoded');
});

// --- 8. the parser -----------------------------------------------------------------------------------------------------

test('the feed parser: entities, a cut-off feed, an API error entry, and linear time on hostile input', async () => {
  const one = L.parseFeed(feed([entryXml('cond-mat/0601001', 1)]));
  assert.equal(one.ok, true);
  assert.equal(one.entries[0].summary, 'Heavy tails of option returns & their pricing.');
  assert.equal(one.entries[0].base, 'cond-mat/0601001');
  assert.deepEqual(one.entries[0].authors, ['Tay Brooks']);
  assert.equal(one.entries[0].primary, 'q-fin.ST');
  assert.equal('comment' in one.entries[0], false);
  const whole = feed([entryXml('1602.00865', 1)]);
  assert.equal(L.parseFeed(whole.slice(0, whole.indexOf('</entry>'))).ok, false);
  assert.equal(L.parseFeed(whole.slice(0, whole.indexOf('</feed>'))).ok, false);
  assert.equal(L.parseFeed('<html>busy</html>').ok, false);
  const error = L.parseFeed(errorFeed('incorrect id format for notanid', '#incorrect_id_format_for_notanid'));
  assert.equal(error.ok, false);
  assert.equal(error.api_error, true);
  assert.match(error.error, /incorrect id format/);
  const legacy = L.parseFeed(errorFeed('x').replace('https://arxiv.org/api/errors', 'http://arxiv.org/api/errors'));
  assert.equal(legacy.api_error, true);
  for (const hostile of ['<feed>' + '<entry'.repeat(6000), '<feed>' + '<entry><id>'.repeat(3000) + '</feed>', '<feed><entry>' + '<category term="'.repeat(4000)]) {
    const began = performance.now();
    L.parseFeed(hostile);
    assert.ok(performance.now() - began < 1000, 'linear, not quadratic');
  }
  const h = harness({ upstream: url => (new URL(url).searchParams.get('search_query') ? atom(errorFeed('Invalid query string'), 400) : null) });
  const refused = await h.search('tail risk');
  assert.equal(refused.status, 502, 'arXiv refused the gateway\'s own query');
  const cut = harness({ upstream: () => atom(whole.slice(0, 600)) });
  assert.equal((await cut.search('tail risk')).status, 502);
  const slow = harness({ upstream: () => new Error('TimeoutError') });
  const timeout = await slow.search('tail risk');
  assert.ok(timeout.status >= 500);
  assert.equal(slow.gate.libraryStatus().upstream, 1, 'it went: it counts');
});

test('email addresses are redacted in one linear pass', () => {
  const cases = {
    'write to a.b-c@dept.univ.edu. Thanks': 'write to [email]. Thanks',
    'x@y and me@site.org, you@x.co.uk': 'x@y and [email], [email]',
    'an @ sign, a@b, @handle': 'an @ sign, a@b, @handle',
    'Email: yuliu3@link.cuhk.edu.cn††thanks': 'Email: [email]††thanks',
  };
  for (const [text, want] of Object.entries(cases)) assert.equal(L.redactEmails(text), want, text);
  const began = performance.now();
  L.redactEmails('a'.repeat(200000) + '@' + 'b'.repeat(200000));
  L.redactEmails('a@'.repeat(100000));
  assert.ok(performance.now() - began < 1000);
});

test('an article with math, headings and no <article> element', () => {
  assert.equal(L.articleOf('<html><body><p>no article</p></body></html>'), null);
  assert.equal(L.articleOf('<articles><article-x>'), null);
  const { text, sections } = L.articleText(L.articleOf(page(article())));
  assert.match(text, /The premium is \\sigma/);
  assert.deepEqual(sections.map(s => s.title), ['1 Introduction', '1.1 Data', '2 Results']);
  for (const s of sections) assert.equal(text.slice(s.start, s.start + s.title.length), s.title);
  const began = performance.now();
  L.mathAsTex('<math alttext="x"'.repeat(20000));
  L.articleText('<article>' + '<h2 class="ltx_title">'.repeat(5000));
  assert.ok(performance.now() - began < 2000);
});

test('the heading scan is linear on malformed headings and bounded on many unmatched ones', () => {
  // Review of #428, gateway F1: `[^>]*` took 3.4 s on 52 KB of `<h2 ` openings with no `>`, in the isolate serving orders.
  let began = performance.now();
  L.articleText('<article>' + '<h2 class="x '.repeat(300_000) + '</article>');
  assert.ok(performance.now() - began < 1000, `3.9 MB of hostile openings: ${performance.now() - began} ms`);
  began = performance.now();
  const past = L.articleText('<article><p>' + 'a '.repeat(160_000) + '</p>' + '<h2 class="ltx_title">zz</h2>'.repeat(100_000) + '</article>');
  assert.ok(performance.now() - began < 1500, `100k headings past the text's cut: ${performance.now() - began} ms`);
  assert.deepEqual(past.sections, []);
  const many = L.articleText('<article>' + Array.from({ length: 200 }, (_, i) => `<h2 class="ltx_title">S${i}</h2><p>x</p>`).join('') + '</article>');
  assert.equal(many.sections.length, L.MAX_SECTIONS);
  assert.ok(L.MAX_HEADINGS >= L.MAX_SECTIONS);
});

test('a page over MAX_PAGE_BYTES is read to its cut and kept: the next read asks nothing', async () => {
  const big = page(article({ extra: 'y '.repeat(L.MAX_PAGE_BYTES) }));
  const h = harness({ upstream: arxiv({ pages: { '2409.06496v1': big } }) });
  const first = await h.read('2409.06496', { chars: '200' });
  assert.equal(first.body.text_source, 'arxiv_html');
  assert.match(first.body.text, /The premium is/);
  assert.ok(first.body.total_chars > 0 && first.body.total_chars <= L.MAX_TEXT_CHARS);
  assert.deepEqual(first.body.sections.map(s => s.title), ['1 Introduction', '1.1 Data']);
  const calls = h.calls.length;
  const second = await h.read('2409.06496v1', { chars: '200' });
  assert.equal(h.calls.length, calls, 'kept: no second 3 MB download');
  assert.equal(second.cache, 'hit');
  assert.equal(L.articleOf('<article class="x"><p>cut her', { partial: true }), '<article class="x"><p>cut her');
  assert.equal(L.articleOf('<article class="x"><p>cut her'), null);
});

test('ar5iv, which is not pinned, is never read from a page cut at MAX_PAGE_BYTES', async () => {
  const big = page(article({ extra: 'y '.repeat(L.MAX_PAGE_BYTES) }));
  const h = harness({ upstream: arxiv({ ar5iv: { '1805.01234': big } }) });
  const { body } = await h.read('1805.01234');
  assert.equal(body.text_source, 'none');
});

// --- 9. the router -----------------------------------------------------------------------------------------------------

test('the routes: the bearer token is required, GET only, the kill switch does not stop them', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  for (const token of [null, 'wrong', TOKEN + '-owner']) {
    const { status } = await h.get(L.PATHS.search, { q: 'tail risk' }, { token });
    assert.equal(status, 401);
  }
  for (const path of [L.PATHS.search, L.PATHS.read, L.PATHS.health]) {
    const { status, response } = await h.get(path, {}, { method: 'POST' });
    assert.equal(status, 405, path);
    assert.equal(response.headers.get('Allow'), 'GET');
  }
  assert.equal(h.calls.length, 0);
  h.gate.setKill(true);
  const { status } = await h.search('tail risk');
  assert.equal(status, 200, 'research moves no money');
  assert.equal((await h.get('/v1/research/other')).status, 404);
});

test('an isolate serves at most MAX_IN_FLIGHT library requests at once; the rest are busy at once', async () => {
  const h = harness({ upstream: arxiv({ hits: ['1602.00865'] }) });
  const answers = await Promise.all(Array.from({ length: L.MAX_IN_FLIGHT + 2 }, (_, i) => h.search(`tail risk ${String.fromCharCode(97 + i)}x`)));
  assert.equal(answers.filter(a => a.status === 429 && a.body.busy).length >= 2, true);
  assert.equal(L.inFlightNow(), 0);
});

// --- the suite's own invariants (run last) ------------------------------------------------------------------------------

test('across the whole suite the upstream saw only allowlisted URLs', () => {
  assert.ok(EVERY_URL.length > 40);
  for (const url of EVERY_URL) assert.equal(L.checkLibraryUrl(url).ok, true, url);
});

test('across the whole suite no answer named a post-cutoff date or the comment\'s address', () => {
  assert.ok(EVERY_ANSWER.length > 60);
  for (const text of EVERY_ANSWER) {
    assert.equal(L.hasPostCutoff(text), false, text.slice(0, 300));
    assert.equal(text.includes(COMMENT_EMAIL), false);
  }
});
