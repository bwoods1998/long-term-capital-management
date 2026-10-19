// R3's births through the docs route (Oct 19, 2026; league/events/births.py): appends of JSON lines to
// docs/births/<YYYY-MM-DD>.jsonl on main and nothing else, the desk's walls (the runtime token, a size cap, the path
// pattern, no credential, New York's day of six), GitHub's commit time in the answer, and a retry that finds its lines
// standing already.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as desk from '../lib/desk.mjs';
import { memoryStore, TOKEN, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';
import { fakeHub } from './autonomy-fixtures.mjs';

const NOW = Date.parse('2026-10-20T01:15:00Z');  // 21:15 in New York: the births job's minute
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const SECRETS = { ALPACA_SECRET_KEY: 'alpaca-secret-that-never-leaves-the-worker', CLAUDE_API_KEY: 'claude-key-held-by-the-gateway-only' };
const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', GITHUB_REPO, GITHUB_TOKEN, CAP_TIMEZONE: 'America/New_York', ...SECRETS, ...extra,
});
const PATH = 'docs/births/2026-10-19.jsonl';
const line = (id, extra = {}) => JSON.stringify({ grammar: 1, sha: 'a'.repeat(64), spec: { id, version: 1 }, why: 'one line', ...extra });
const post = (body, token = TOKEN) => new Request(`${GATEWAY}/v1/github/docs`, {
  method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: typeof body === 'string' ? body : JSON.stringify(body),
});
const call = async (request, { gate, hub, at = NOW }) => {
  const response = await route(request, env(), { gate, fetcher: hub.fetcher, now: () => at });
  return { response, body: await response.clone().json().catch(() => null) };
};
const gateAt = () => createGate({ store: memoryStore(), env: env(), now: () => NOW });
const puts = hub => hub.calls.filter(made => made.method === 'PUT');

test('only docs/births/<real date>.jsonl is a births file, and only lines are appended to it', () => {
  for (const path of [PATH, 'docs/births/2024-02-29.jsonl']) assert.equal(desk.admitBirths({ path, lines: [line('EVL-B-A')] }).path, path);
  for (const path of ['docs/births/2026-02-30.jsonl', 'docs/births/2026-13-01.jsonl', 'docs/births/2026-10-9.jsonl',
    'docs/births/2026-10-19.json', 'docs/births/2026-10-19.JSONL', 'docs/births/2026-10-19-x.jsonl', 'docs/births/../births/2026-10-19.jsonl',
    'docs/births/sub/2026-10-19.jsonl', 'docs/births/2026-10-19.jsonl\n', 'docs/births/', 'docs/birth/2026-10-19.jsonl',
    'docs/runs/desk/2026-10-19.md', 'league/events/programs.py', '/docs/births/2026-10-19.jsonl', '', null, 5]) {
    const refused = desk.admitBirths({ path, lines: [line('EVL-B-A')] });
    assert.equal(refused.status, 403, JSON.stringify(path));
    assert.equal(refused.refused, 'path');
  }
  const whole = desk.admitBirths({ path: PATH, content: `${line('EVL-B-A')}\n` });
  assert.deepEqual([whole.status, whole.refused], [403, 'append'], 'a whole content is never written to a births file');
  assert.equal(desk.admitBirths({ path: PATH, content: 'x', lines: [line('EVL-B-A')] }).refused, 'append');
});

test('each line is one JSON object of at most 8 KB; 1 to 12 lines, none repeated; the message births: one line', () => {
  const ok = desk.admitBirths({ path: PATH, lines: [line('EVL-B-A'), line('EVL-B-B')] });
  assert.deepEqual(ok.lines, [line('EVL-B-A'), line('EVL-B-B')]);
  assert.equal(ok.message, `births: 2 birth(s)\n\n${desk.FOOTER}`);
  assert.equal(desk.admitBirths({ path: PATH, lines: [line('A')], message: 'Births:  3 of the night' }).message.split('\n')[0], 'births: 3 of the night');
  for (const lines of [[], undefined, 'x', [line('A')].concat(Array.from({ length: 12 }, (_, i) => line(`B${i}`))), [5], [''],
    ['[1, 2]'], ['"text"'], ['null'], ['{"a": 1'], ['{"a":1}\n{"b":2}'], ['{"a":" "}'], ['{"a":\t1}'], [line('A'), line('A')]]) {
    const refused = desk.admitBirths({ path: PATH, lines });
    assert.equal(refused.status, 400, JSON.stringify(lines)?.slice(0, 60));
    assert.ok(['lines', 'json'].includes(refused.refused), JSON.stringify(refused));
  }
  const big = desk.admitBirths({ path: PATH, lines: [JSON.stringify({ why: 'x'.repeat(8 * 1024) })] });
  assert.deepEqual([big.status, big.refused], [413, 'size']);
  for (const message of ['two\nlines', '', 'births:', 'x'.repeat(101), 7]) {
    assert.equal(desk.admitBirths({ path: PATH, lines: [line('A')], message }).refused, 'message', JSON.stringify(message));
  }
  for (const body of [null, [], 'text']) assert.equal(desk.admitBirths(body).status, 400);
});

test('a line carrying a credential this gateway holds, or key-shaped text, is never committed', () => {
  const e = env();
  for (const why of [SECRETS.ALPACA_SECRET_KEY, GITHUB_TOKEN, `x ${TOKEN} y`, `sk-ant-${'c'.repeat(40)}`, `ghp_${'A'.repeat(36)}`]) {
    const refused = desk.admitBirths({ path: PATH, lines: [line('EVL-B-A', { why })] }, e);
    assert.deepEqual([refused.status, refused.refused], [403, 'secret'], why.slice(0, 20));
  }
  assert.equal(desk.admitBirths({ path: PATH, lines: [line('A')], message: `see ${SECRETS.CLAUDE_API_KEY}` }, e).refused, 'secret');
});

test('the append: a first file, then lines after what main holds; never a rewrite; GitHub\'s commit time in the answer', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  const first = await call(post({ path: PATH, lines: [line('EVL-B-A'), line('EVL-B-B')], message: '2 of 2026-10-19' }), { gate, hub });
  assert.equal(first.response.status, 200, JSON.stringify(first.body));
  assert.deepEqual(first.body, { ok: true, committed: true, path: PATH, commit: hub.commits[0].commit,
    committed_at: '2026-10-19T01:15:07Z', lines: 2, docs_today: 1 });
  assert.equal(hub.contents.get(PATH), `${line('EVL-B-A')}\n${line('EVL-B-B')}\n`);
  const [put] = puts(hub);
  assert.equal(put.url, `https://api.github.com/repos/${GITHUB_REPO}/contents/${PATH}`);
  assert.deepEqual(Object.keys(put.body).sort(), ['branch', 'content', 'message'], 'a new file: no blob replaced');
  assert.equal(put.body.branch, 'main');
  assert.equal(put.body.message, `births: 2 of 2026-10-19\n\n${desk.FOOTER}`);

  hub.clock = () => '2026-10-19T02:00:00Z';
  const second = await call(post({ path: PATH, lines: [line('EVL-B-C')] }), { gate, hub });
  assert.equal(second.response.status, 200, JSON.stringify(second.body));
  assert.equal(second.body.committed_at, '2026-10-19T02:00:00Z');
  assert.equal(puts(hub)[1].body.sha, desk.blobSha(`${line('EVL-B-A')}\n${line('EVL-B-B')}\n`), 'the blob it appends to');
  assert.equal(hub.contents.get(PATH), `${line('EVL-B-A')}\n${line('EVL-B-B')}\n${line('EVL-B-C')}\n`, 'appended, never rewritten');
  assert.equal(gate.status(NOW).autonomy.docs.commits, 2);
});

test('lines that all stand on main already commit nothing and take no place: the answer names the file\'s latest commit', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub });
  hub.clock = () => '2026-10-19T03:00:00Z';
  await call(post({ path: PATH, lines: [line('EVL-B-B')] }), { gate, hub });
  const again = await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub });
  assert.equal(again.response.status, 200, JSON.stringify(again.body));
  assert.deepEqual(again.body, { ok: true, committed: false, unchanged: true, path: PATH, commit: hub.commits[1].commit,
    committed_at: '2026-10-19T03:00:00Z', lines: 1 }, 'the latest commit: no earlier than the one that added the line');
  assert.equal(puts(hub).length, 2, 'no commit');
  assert.equal(gate.status(NOW).autonomy.docs.commits, 2, 'and no place taken');
  const mixed = await call(post({ path: PATH, lines: [line('EVL-B-A'), line('EVL-B-Z')] }), { gate, hub });
  assert.deepEqual([mixed.response.status, mixed.body.refused], [409, 'duplicate']);
  assert.equal(puts(hub).length, 2);
});

test('a births file that is not whole lines, a folder, or one past 256 KB is refused; GitHub unread takes no place', async () => {
  const gate = gateAt();
  const broken = fakeHub();
  broken.contents.set(PATH, '{"a":1}');
  const odd = await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub: broken });
  assert.deepEqual([odd.response.status, odd.body.refused], [409, 'shape']);
  const full = fakeHub();
  full.contents.set(PATH, `${JSON.stringify({ pad: 'x'.repeat(desk.BIRTHS_FILE_MAX_BYTES - 20) })}\n`);
  const over = await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub: full });
  assert.deepEqual([over.response.status, over.body.refused], [413, 'size']);
  const folder = fakeHub({ script: key => (key.startsWith('GET /contents') ? new Response(JSON.stringify([{ name: 'x' }]), { status: 200 }) : undefined) });
  assert.equal((await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub: folder })).body.refused, 'path');
  const down = fakeHub({ script: key => (key.startsWith('GET /contents') ? new Response('{}', { status: 500 }) : undefined) });
  assert.equal((await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub: down })).response.status, 502);
  const unsized = fakeHub({ script: key => (key.startsWith('GET /contents') ? new Response(JSON.stringify({ type: 'file', sha: 'c'.repeat(40), encoding: 'none', content: '' }), { status: 200 }) : undefined) });
  assert.equal((await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub: unsized })).body.refused, 'size');
  for (const hub of [broken, full, folder, down, unsized]) assert.equal(puts(hub).length, 0);
  assert.equal(gate.status(NOW).autonomy.docs.commits, 0, 'nothing reached GitHub, no place taken');
});

test('GitHub\'s no gives the place back; no answer keeps it; the day\'s six are shared with the desk pages', async () => {
  const gate = gateAt();
  const conflict = fakeHub({ script: key => (key.startsWith('PUT ') ? new Response(JSON.stringify({ message: `conflict ${GITHUB_TOKEN}` }), { status: 409 }) : undefined) });
  const refused = await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub: conflict });
  assert.deepEqual([refused.response.status, refused.body.refused], [409, 'github']);
  assert.equal(JSON.stringify(refused.body).includes(GITHUB_TOKEN), false, 'never the token');
  assert.equal(gate.status(NOW).autonomy.docs.commits, 0);
  const silent = fakeHub({ script: key => (key.startsWith('PUT ') ? Promise.reject(new Error('reset')) : undefined) });
  const lost = await call(post({ path: PATH, lines: [line('EVL-B-A')] }), { gate, hub: silent });
  assert.deepEqual([lost.response.status, lost.body.refused], [502, 'no_answer']);
  assert.equal(gate.status(NOW).autonomy.docs.commits, 1, 'it may have committed');
  const hub = fakeHub();
  for (let n = 2; n <= 6; n += 1) {
    const page = await call(post({ path: `docs/runs/desk/2026-10-19-page-${n}.md`, content: `page ${n}\n` }), { gate, hub });
    assert.equal(page.response.status, 200, `page ${n}`);
  }
  const capped = await call(post({ path: PATH, lines: [line('EVL-B-B')] }), { gate, hub });
  assert.deepEqual([capped.response.status, capped.body.cap], [429, 'docs_day']);
});

test('the route is POST behind the runtime token; a desk page and its answer are as before; no other path', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  assert.equal((await call(post({ path: PATH, lines: [line('EVL-B-A')] }, 'wrong'), { gate, hub })).response.status, 401);
  assert.equal((await call(new Request(`${GATEWAY}/v1/github/docs`, { headers: { Authorization: `Bearer ${TOKEN}` } }), { gate, hub })).response.status, 405);
  for (const path of ['docs/prereg/PREREG-EVL-4.md', 'league/events/screen.py', 'docs/births.jsonl', 'docs/births/2026-10-19.md']) {
    const no = await call(post({ path, lines: [line('EVL-B-A')], content: 'x' }), { gate, hub });
    assert.equal(no.response.status, 403, path);
  }
  const page = await call(post({ path: 'docs/runs/desk/2026-10-19.md', content: 'desk\n' }), { gate, hub });
  assert.deepEqual(Object.keys(page.body).sort(), ['commit', 'committed', 'docs_today', 'ok', 'path'], 'the desk answer is unchanged');
  assert.equal(hub.calls.filter(made => made.method === 'PUT').length, 1);
});
