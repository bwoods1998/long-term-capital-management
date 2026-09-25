// The research web reader (`POST /v1/web/fetch`): what it refuses to read, what it sends, what it
// answers, and how many pages a day the floor may read. Every upstream here is a stand-in: the
// suite touches no network.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as web from '../lib/fetch.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-09-26T16:00:00Z');
const GATEWAY = 'https://ltcm-gateway.bw.workers.dev';
const env = { GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner' };

const gateFor = (store = memoryStore()) => createGate({ store, env, now: () => NOW });

const ask = (body, { token = TOKEN, method = 'POST', headers = {} } = {}) =>
  new Request(GATEWAY + web.PATH, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), 'Content-Type': 'application/json', ...headers },
    ...(method === 'POST' ? { body: typeof body === 'string' ? body : JSON.stringify(body) } : {}),
  });

// A body given as bytes, so a page with no content type really has none (a string body would get text/plain).
const page = (body, { status = 200, type = 'text/html; charset=utf-8', headers = {} } = {}) =>
  new Response(typeof body === 'string' ? new TextEncoder().encode(body) : body,
    { status, headers: { ...(type ? { 'Content-Type': type } : {}), ...headers } });

const redirect = (location, status = 302) => new Response(null, { status, headers: { Location: location } });

/** An upstream that answers by URL (`replies[url]`, a Response or a function) and records every call. */
function upstream(replies) {
  const calls = [];
  const fetcher = async (url, options = {}) => {
    calls.push({ url: String(url), ...options });
    const reply = typeof replies === 'function' ? replies(String(url), options) : replies[String(url)];
    if (reply instanceof Error) throw reply;
    if (!reply) return page('not scripted', { status: 404, type: 'text/plain' });
    return typeof reply === 'function' ? reply(options) : reply;
  };
  return { fetcher, calls };
}

const call = async (body, { replies = {}, gate = gateFor(), options = {} } = {}) => {
  const tape = upstream(replies);
  const response = await route(ask(body, options), env, { gate, fetcher: tape.fetcher, now: () => NOW });
  return { response, calls: tape.calls, gate, body: await response.clone().json().catch(() => null) };
};

// --- who may ask --------------------------------------------------------------------------------

test('a fetch without the runtime token reads nothing and counts nothing', async () => {
  for (const token of [null, 'wrong', TOKEN + '-owner']) {
    const { response, calls, gate } = await call({ url: 'https://example.com/' }, { options: { token } });
    assert.equal(response.status, 401);
    assert.equal(calls.length, 0);
    assert.equal(gate.webFetchDay(NOW).count, 0);
  }
});

test('only POST, with a JSON body that names a url', async () => {
  const get = await call(null, { options: { method: 'GET' } });
  assert.equal(get.response.status, 405);
  assert.equal(get.response.headers.get('Allow'), 'POST');
  for (const body of ['not json', '[]', '{}', '{"url": ""}', '{"url": 7}']) {
    const { response, calls, body: answer } = await call(body);
    assert.equal(response.status, 400, body);
    assert.equal(calls.length, 0);
    assert.equal('url' in answer, false, 'a request the gateway could not read names no url');
  }
  const huge = await call({ url: 'https://example.com/', agent: 'x'.repeat(9000) });
  assert.equal(huge.response.status, 413);
});

// --- what it refuses to read --------------------------------------------------------------------

const REFUSED = {
  'ftp://example.com/file.txt': /http and https/,
  'file:///etc/passwd': /http and https/,
  'javascript:alert(1)': /http and https/,
  'data:text/html,<p>hi</p>': /http and https/,
  'gopher://example.com/': /http and https/,
  'http://example.com:8080/': /default port/,
  'https://example.com:80/': /default port/,
  'http://example.com:443/': /default port/,
  'http://user:secret@example.com/': /user or password/,
  'https://user@example.com/': /user or password/,
  'http://127.0.0.1/': /loopback/,
  'http://127.8.9.10:80/': /loopback/,
  'http://2130706433/': /loopback/,
  'http://0x7f.1/': /loopback/,
  'http://0177.0.0.1/': /loopback/,
  'http://127.1/': /loopback/,
  'http://10.1.2.3/': /private/,
  'http://172.16.0.9/': /private/,
  'http://172.31.255.255/': /private/,
  'http://192.168.1.1/': /private/,
  'http://169.254.169.254/latest/meta-data/iam/': /metadata address/,
  'http://169.254.1.1/': /link-local/,
  'http://100.64.0.1/': /CGNAT/,
  'http://100.127.255.254/': /CGNAT/,
  'http://224.0.0.251/': /multicast/,
  'http://239.255.255.250/': /multicast/,
  'http://0.0.0.0/': /unspecified/,
  'http://0/': /unspecified/,
  'http://255.255.255.255/': /reserved/,
  'http://240.0.0.1/': /reserved/,
  'http://192.0.2.1/': /reserved/,
  'http://[::1]/': /loopback/,
  'http://[0:0:0:0:0:0:0:1]/': /loopback/,
  'http://[::]/': /unspecified/,
  'http://[::ffff:127.0.0.1]/': /IPv4-mapped/,
  'http://[::ffff:a9fe:a9fe]/': /IPv4-mapped/,
  'http://[::ffff:10.0.0.1]/': /IPv4-mapped/,
  'http://[::127.0.0.1]/': /non-global/,
  'http://[fd00::1]/': /unique-local/,
  'http://[fc00:1234::1]/': /unique-local/,
  'http://[fe80::1]/': /link-local/,
  'http://[ff02::1]/': /multicast/,
  'http://[64:ff9b::a9fe:a9fe]/': /non-global/,
  'http://[2001:db8::1]/': /reserved/,
  'http://[2001:0:4136:e378::1]/': /reserved/,
  'http://[2002:a9fe:a9fe::1]/': /reserved/,
  'http://localhost/': /local or internal/,
  'http://LOCALHOST./admin': /local or internal/,
  'http://api.localhost/': /local or internal/,
  'http://printer.local/': /local or internal/,
  'http://metadata.google.internal/computeMetadata/v1/': /local or internal/,
  'http://db.corp.internal/': /local or internal/,
  'http://nas.home.arpa/': /local or internal/,
  'http://intranet/': /no domain/,
  'https://ltcm-gateway.bw.workers.dev/v1/health': /own domain/,
  'https://LTCM-GATEWAY.bw.workers.dev./v1/kill': /own domain/,
  'https://another-worker.bw.workers.dev/': /own domain/,
  'not a url': /cannot be parsed/,
  ['https://example.com/' + 'a'.repeat(2048)]: /longer than 2048/,
};

test('every refused url class is refused before anything is fetched or counted', async () => {
  const gate = gateFor();
  for (const [url, why] of Object.entries(REFUSED)) {
    const { response, calls, body } = await call({ url, agent: 'kalshi-sports-1' }, { gate });
    assert.equal(response.status, 403, url);
    assert.equal(body.refused, 'url', url);
    assert.match(body.error, why, url);
    assert.equal(typeof body.url, 'string', 'a judged url is named in the answer');
    assert.equal(calls.length, 0, url);
  }
  assert.equal(gate.webFetchDay(NOW).count, 0, 'a refused url takes none of the day\'s places');
});

test('public urls pass the rules, fragment dropped', () => {
  const own = web.ownDomains('ltcm-gateway.bw.workers.dev');
  assert.deepEqual(own, ['ltcm-gateway.bw.workers.dev', 'bw.workers.dev']);
  for (const [url, href] of [
    ['https://en.wikipedia.org/wiki/Kalshi#History', 'https://en.wikipedia.org/wiki/Kalshi'],
    ['http://example.com:80/a?b=1', 'http://example.com/a?b=1'],
    ['https://example.com:443/', 'https://example.com/'],
    ['http://93.184.216.34/', 'http://93.184.216.34/'],
    ['http://8.8.8.8/', 'http://8.8.8.8/'],
    ['http://[2606:4700:4700::1111]/', 'http://[2606:4700:4700::1111]/'],
    ['https://someone-else.workers.dev/', 'https://someone-else.workers.dev/'],
    ['https://site.example.com/', 'https://site.example.com/'],
    ['  https://example.com/padded  ', 'https://example.com/padded'],
  ]) {
    const checked = web.checkUrl(url, own);
    assert.equal(checked.error, undefined, url);
    assert.equal(checked.url.href, href);
  }
});

// --- redirects ----------------------------------------------------------------------------------

test('a public page that redirects to a private address is refused at the hop', async () => {
  for (const target of ['http://169.254.169.254/latest/meta-data/', 'http://localhost:8080/', 'http://[::1]/', 'ftp://example.com/',
    'http://10.0.0.5/', 'https://ltcm-gateway.bw.workers.dev/v1/health', 'http://user:pw@example.org/']) {
    const { response, calls, body, gate } = await call({ url: 'https://example.com/go' }, {
      replies: { 'https://example.com/go': redirect(target) },
    });
    assert.equal(response.status, 403, target);
    assert.equal(body.refused, 'redirect');
    assert.equal(body.final_url, 'https://example.com/go');
    assert.equal(calls.length, 1, `only the public page was asked (${target})`);
    assert.equal(gate.webFetchDay(NOW).count, 1, 'a fetch that reached the open web is counted');
  }
});

test('redirects are followed by hand, relative ones resolved, at most five', async () => {
  const replies = {
    'https://a.example/0': redirect('/1', 301),
    'https://a.example/1': redirect('https://b.example/2', 308),
    'https://b.example/2': redirect('3', 307),
    'https://b.example/3': redirect('//c.example/4', 303),
    'https://c.example/4': redirect('http://d.example/5'),
    'http://d.example/5': page('<title>Landed</title><p>five hops</p>'),
  };
  const { response, body, calls } = await call({ url: 'https://a.example/0' }, { replies });
  assert.equal(response.status, 200);
  assert.equal(body.final_url, 'http://d.example/5');
  assert.equal(body.url, 'https://a.example/0');
  assert.equal(body.title, 'Landed');
  assert.equal(calls.length, 6);
  assert.ok(calls.every(c => c.redirect === 'manual' && c.method === 'GET'));

  const loop = await call({ url: 'https://loop.example/0' }, {
    replies: url => redirect(`/${Number(new URL(url).pathname.slice(1)) + 1}`),
  });
  assert.equal(loop.response.status, 502);
  assert.match(loop.body.error, /more than 5/);
  assert.equal(loop.calls.length, 6);
});

// --- what it sends ------------------------------------------------------------------------------

test('no credential of any kind is forwarded, on the request or on a hop', async () => {
  const { response, calls } = await call({ url: 'https://example.com/a' }, {
    replies: { 'https://example.com/a': redirect('https://example.com/b'), 'https://example.com/b': page('<p>ok</p>') },
    options: { headers: { Cookie: 'session=abc', 'X-Api-Key': 'k', 'Proxy-Authorization': 'Basic eA==' } },
  });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  for (const sent of calls) {
    assert.deepEqual(sent.headers, {
      'User-Agent': 'LTCM-research/1.0 (+https://blakewoods.us/capital)',
      Accept: web.ACCEPT,
      'Accept-Language': 'en',
    });
    assert.equal(sent.method, 'GET');
    assert.equal(sent.body, undefined);
    assert.equal(sent.credentials, undefined);
    assert.ok(sent.signal instanceof AbortSignal);
    assert.doesNotMatch(JSON.stringify(sent.headers), new RegExp(TOKEN));
  }
});

// --- what it answers ----------------------------------------------------------------------------

const HTML = `<!DOCTYPE html>
<html><head>
  <meta charset="utf-8"><title> Kalshi &amp; the   NFL </title>
  <style>body { color: red }</style>
  <script>window.secret = "never shown";</script>
  <meta name="description" content="HEAD META TEXT">
</head>
<body>
  <!-- a comment that is not text -->
  <nav><a href="/home">Home</a> | <a href="/data" title="a > b">Data &raquo;</a></nav>
  <h1>Week&nbsp;4   odds</h1>
  <p>Favorites won <b>62%</b> of games &mdash; see <a href="https://example.com/x">the table</a>.</p>
  <script type="application/ld+json">{"hidden": true}</script>
  <noscript>Enable JavaScript</noscript>
  <svg><text>chart label</text></svg>
  <template><p>inert</p></template>
  <ul><li>Chiefs &lt;-3.5&gt;</li><li>Bills &#8722;2 &#x2713;</li></ul>
  <table><tr><th>Team</th><th>Win %</th></tr><tr><td>KC</td><td>0.71</td></tr></table>
</body></html>`;

test('an HTML page becomes its title and readable text', async () => {
  const { response, body } = await call({ url: 'https://example.com/odds', agent: 'nfl-model-2' }, {
    replies: { 'https://example.com/odds': page(HTML) },
  });
  assert.equal(response.status, 200);
  assert.deepEqual(Object.keys(body), ['url', 'final_url', 'status', 'content_type', 'title', 'text', 'truncated', 'bytes', 'fetched_at']);
  assert.equal(body.title, 'Kalshi & the NFL');
  assert.equal(body.status, 200);
  assert.equal(body.content_type, 'text/html');
  assert.equal(body.truncated, false);
  assert.equal(body.bytes, new TextEncoder().encode(HTML).length);
  assert.equal(body.fetched_at, '2026-09-26T16:00:00.000Z');
  const text = body.text;
  for (const kept of ['Home', 'Data »', 'Week 4 odds', 'Favorites won 62% of games — see the table.', '- Chiefs <-3.5>', '- Bills −2 ✓',
    'Team | Win %', 'KC | 0.71']) {
    assert.ok(text.includes(kept), `${kept} is in ${JSON.stringify(text)}`);
  }
  for (const dropped of ['never shown', 'color: red', 'HEAD META', 'hidden', 'Enable JavaScript', 'chart label', 'inert', 'comment', '<', 'href']) {
    assert.ok(!text.replace('<-3.5>', '').includes(dropped), `${dropped} is not in the text`);
  }
  assert.doesNotMatch(text, / {2}|\n{3}/, 'whitespace is collapsed');
});

test('a head left unclosed is dropped only up to the body', () => {
  const { title, text } = web.htmlToText('<html><head><title>T</title><link rel=x><body><p>Body text</p>');
  assert.equal(title, 'T');
  assert.equal(text, 'Body text');
  assert.equal(web.htmlToText('<p>No head at all</p>').text, 'No head at all');
  assert.equal(web.htmlToText('<p>before</p><script>unclosed(').text, 'before');
});

test('JSON, XML and plain text come back as text', async () => {
  const replies = {
    'https://api.example/j': page('{"games": [{"home": "KC", "p": 0.71}]}', { type: 'application/json' }),
    'https://api.example/x': page('<rss><item><title>News</title></item></rss>', { type: 'application/rss+xml; charset=utf-8' }),
    'https://api.example/t': page('  plain\ntext  ', { type: 'text/plain' }),
    'https://api.example/c': page('a,b\n1,2', { type: 'text/csv' }),
  };
  const json = await call({ url: 'https://api.example/j' }, { replies });
  assert.equal(json.body.text, '{"games": [{"home": "KC", "p": 0.71}]}');
  assert.equal(json.body.title, '');
  assert.equal((await call({ url: 'https://api.example/x' }, { replies })).body.text, '<rss><item><title>News</title></item></rss>');
  assert.equal((await call({ url: 'https://api.example/t' }, { replies })).body.text, 'plain\ntext');
  assert.equal((await call({ url: 'https://api.example/c' }, { replies })).body.content_type, 'text/csv');
});

test('a page that answers non-2xx is an answer with its status', async () => {
  const { response, body, gate } = await call({ url: 'https://example.com/missing' }, {
    replies: { 'https://example.com/missing': page('<title>Not Found</title><p>No such page</p>', { status: 404 }) },
  });
  assert.equal(response.status, 200);
  assert.equal(body.status, 404);
  assert.equal(body.text, 'No such page');
  assert.equal(gate.webFetchDay(NOW).count, 1);
});

test('a content type it does not read is refused, naming the type', async () => {
  for (const [type, named] of [['application/pdf', 'application/pdf'], ['image/png', 'image/png'],
    ['application/octet-stream', 'application/octet-stream'], [null, '(none)']]) {
    const { response, body } = await call({ url: 'https://example.com/file' }, {
      replies: { 'https://example.com/file': page('%PDF-1.7', { type }) },
    });
    assert.equal(response.status, 415, String(type));
    assert.ok(body.error.includes(named), body.error);
    assert.equal(body.status, 200);
    assert.equal(body.url, 'https://example.com/file');
  }
});

test('the text is capped at 200,000 characters and marked truncated', async () => {
  const long = 'x'.repeat(web.MAX_TEXT_CHARS + 500);
  const { body } = await call({ url: 'https://example.com/long' }, {
    replies: { 'https://example.com/long': page(long, { type: 'text/plain' }) },
  });
  assert.equal(body.text.length, web.MAX_TEXT_CHARS);
  assert.equal(body.truncated, true);
  // Never half a character: a surrogate pair at the cut is left out whole.
  const emoji = 'y'.repeat(web.MAX_TEXT_CHARS - 1) + '😀tail';
  const cut = await call({ url: 'https://example.com/emoji' }, {
    replies: { 'https://example.com/emoji': page(emoji, { type: 'text/plain' }) },
  });
  assert.equal(cut.body.text.length, web.MAX_TEXT_CHARS - 1);
});

test('the body is read to 2 MB and no further', async () => {
  let pulled = 0;
  const endless = () => new ReadableStream({
    pull(controller) {
      pulled += 1;
      controller.enqueue(new TextEncoder().encode('z'.repeat(64 * 1024)));
    },
  });
  const { body } = await call({ url: 'https://example.com/endless' }, {
    replies: { 'https://example.com/endless': () => page(endless(), { type: 'text/plain' }) },
  });
  assert.equal(body.bytes, web.MAX_BODY_BYTES);
  assert.equal(body.truncated, true);
  assert.ok(pulled <= web.MAX_BODY_BYTES / (64 * 1024) + 2, `stopped reading after ${pulled} chunks`);
});

test('a page that does not answer in time is a 504, one that fails is a 502', async () => {
  const hang = (url, options) => new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason)));
  const slow = await web.webFetch(ask({ url: 'https://slow.example/' }), env, { gate: gateFor(), fetcher: hang, now: () => NOW, timeoutMs: 30 });
  assert.equal(slow.status, 504);
  assert.equal((await slow.json()).url, 'https://slow.example/');

  const trickle = () => page(new ReadableStream({ pull: () => new Promise(() => {}) }), { type: 'text/plain' });
  const stuck = await web.webFetch(ask({ url: 'https://stuck.example/' }), env, { gate: gateFor(), fetcher: trickle, now: () => NOW, timeoutMs: 30 });
  assert.equal(stuck.status, 504, 'a body that stops mid-read is cut off at the deadline');

  const { response, body } = await call({ url: 'https://down.example/' }, { replies: { 'https://down.example/': new TypeError('fetch failed') } });
  assert.equal(response.status, 502);
  assert.match(body.error, /could not be read: TypeError/);
  assert.equal(body.url, 'https://down.example/');
});

// --- the day's cap ------------------------------------------------------------------------------

test('the floor reads at most DAY_CAP pages a UTC day, counted by agent, and health reports it', async () => {
  const store = memoryStore();
  const gate = gateFor(store);
  const replies = { 'https://example.com/': () => page('<p>hi</p>') };
  await call({ url: 'https://example.com/', agent: 'nfl-model-2' }, { gate, replies });
  await call({ url: 'https://example.com/', agent: 'nfl-model-2' }, { gate, replies });
  await call({ url: 'https://example.com/', agent: 'Not A Name!' }, { gate, replies });
  const health = await route(new Request(GATEWAY + '/v1/health', { headers: { Authorization: `Bearer ${TOKEN}` } }), env, { gate, now: () => NOW });
  assert.deepEqual((await health.json()).web_fetch,
    { day: '2026-09-26', fetches: 3, cap: web.DAY_CAP, by_agent: { 'nfl-model-2': 2, unattributed: 1 } });

  store.set('web-fetch', JSON.stringify({ day: '2026-09-26', count: web.DAY_CAP, by_agent: {} }));
  const full = await call({ url: 'https://example.com/' }, { gate, replies });
  assert.equal(full.response.status, 429);
  assert.equal(full.body.cap, 'web_fetch_day');
  assert.equal(full.response.headers.get('Retry-After'), '3600');
  assert.equal(full.calls.length, 0);
  assert.equal('url' in full.body, false, 'a fetch the gateway could not make names no url');

  // Yesterday's count is not today's.
  store.set('web-fetch', JSON.stringify({ day: '2026-09-25', count: web.DAY_CAP, by_agent: {} }));
  assert.equal((await call({ url: 'https://example.com/' }, { gate, replies })).response.status, 200);
  assert.equal(gate.webFetchDay(NOW).count, 1);
});

test('the kill switch does not stop a page from being read', async () => {
  const gate = gateFor();
  gate.setKill(true);
  const { response, body } = await call({ url: 'https://example.com/' }, { gate, replies: { 'https://example.com/': page('<p>still reading</p>') } });
  assert.equal(response.status, 200);
  assert.equal(body.text, 'still reading');
});
