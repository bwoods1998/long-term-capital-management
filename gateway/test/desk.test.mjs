// The desk's docs commits (V3-A, WP8): one page under docs/runs/desk/ committed to main, its walls (path, size, text,
// message, credentials), New York's day of six, and what a retry or a GitHub refusal costs.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as desk from '../lib/desk.mjs';
import { memoryStore, TOKEN, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';
import { fakeHub } from './autonomy-fixtures.mjs';

const NOW = Date.parse('2026-10-05T23:30:00Z');  // 19:30 in New York: the scoreboard's hour
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const SECRETS = { ALPACA_SECRET_KEY: 'alpaca-secret-that-never-leaves-the-worker', CLAUDE_API_KEY: 'claude-key-held-by-the-gateway-only' };
const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', GITHUB_REPO, GITHUB_TOKEN, CAP_TIMEZONE: 'America/New_York', ...SECRETS, ...extra,
});
const PAGE = '# Desk 2026-10-05\n\nRelease: abc1234. Jobs ran 7 of 7; missed 0.\n';
const post = (body, token = TOKEN) => new Request(`${GATEWAY}/v1/github/docs`, {
  method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: typeof body === 'string' ? body : JSON.stringify(body),
});
const call = async (request, { gate, hub, at = NOW }) => {
  const response = await route(request, env(), { gate, fetcher: hub.fetcher, now: () => at });
  return { response, body: await response.clone().json().catch(() => null) };
};
const gateAt = () => createGate({ store: memoryStore(), env: env(), now: () => NOW });
const puts = hub => hub.calls.filter(made => made.method === 'PUT');

test('only docs/runs/desk/<real date>[-slug].md is a desk page', () => {
  for (const path of ['docs/runs/desk/2026-10-05.md', 'docs/runs/desk/2026-10-05-scoreboard.md', 'docs/runs/desk/2024-02-29-run-record-2.md']) {
    assert.equal(desk.admitDoc({ path, content: PAGE }).path, path, path);
  }
  for (const path of ['docs/runs/desk/2026-02-30.md', 'docs/runs/desk/2026-13-01.md', 'docs/runs/desk/2026-10-5.md',
    'docs/runs/desk/2026-10-05.MD', 'docs/runs/desk/2026-10-05-Score.md', 'docs/runs/desk/2026-10-05_x.md', 'docs/runs/desk/2026-10-05-.md.md',
    'docs/runs/desk/../desk/2026-10-05.md', 'docs/runs/desk/sub/2026-10-05.md', 'docs/runs/2026-10-05.md', 'docs/design.md', 'README.md',
    'league/constitution.py', '/docs/runs/desk/2026-10-05.md', 'docs/runs/desk/2026-10-05.md\n', 'docs/runs/desk/2026-10-05.txt', '', null, 5]) {
    const refused = desk.admitDoc({ path, content: PAGE });
    assert.equal(refused.status, 403, JSON.stringify(path));
    assert.equal(refused.refused, 'path');
  }
});

test('the content is UTF-8 text of at most 64 KB; the message one line, prefixed desk:', () => {
  const path = 'docs/runs/desk/2026-10-05.md';
  assert.equal(desk.admitDoc({ path, content: 'é'.repeat(32 * 1024) }).content.length, 32 * 1024, 'exactly 64 KB of two-byte text');
  assert.equal(desk.admitDoc({ path, content: 'x'.repeat(64 * 1024 + 1) }).status, 413);
  assert.equal(desk.admitDoc({ path, content: 'é'.repeat(32 * 1024) + 'x' }).status, 413);
  for (const content of ['', 'a\u0000b', '\ud800 lone surrogate', 42, null, ['x']]) {
    assert.equal(desk.admitDoc({ path, content }).refused, 'content', JSON.stringify(content));
  }
  assert.equal(desk.admitDoc({ path, content: PAGE }).message, `desk: 2026-10-05.md\n\n${desk.FOOTER}`);
  assert.equal(desk.admitDoc({ path, content: PAGE, message: 'scoreboard for Oct 5' }).message.split('\n')[0], 'desk: scoreboard for Oct 5');
  assert.equal(desk.admitDoc({ path, content: PAGE, message: 'Desk:  scoreboard' }).message.split('\n')[0], 'desk: scoreboard', 'one prefix');
  for (const message of ['two\nlines', 'tab\there', '', '   ', 'desk:', 'x'.repeat(101), 7]) {
    assert.equal(desk.admitDoc({ path, content: PAGE, message }).refused, 'message', JSON.stringify(message));
  }
  for (const body of [null, [], 'text']) assert.equal(desk.admitDoc(body).status, 400);
});

test('a page carrying a credential this gateway holds, or text shaped like any key, is never committed', () => {
  const path = 'docs/runs/desk/2026-10-05.md';
  const e = env();
  for (const content of [
    `${PAGE}\nleaked: ${SECRETS.ALPACA_SECRET_KEY}\n`, `${PAGE}${GITHUB_TOKEN}`, `x ${TOKEN} y`, `${SECRETS.CLAUDE_API_KEY}`,
    '-----BEGIN PRIVATE KEY-----\nMIIE\n', '-----BEGIN RSA PRIVATE KEY-----', `token ghp_${'A'.repeat(36)}`,
    `github_pat_${'b'.repeat(40)}`, `sk-ant-${'c'.repeat(40)}`, `key sk-proj-${'d'.repeat(30)}`,
  ]) {
    const refused = desk.admitDoc({ path, content }, e);
    assert.equal(refused.status, 403, content.slice(0, 40));
    assert.equal(refused.refused, 'secret');
  }
  assert.equal(desk.admitDoc({ path, content: PAGE, message: `see ${SECRETS.CLAUDE_API_KEY}` }, e).refused, 'secret');
  // Ordinary desk words are not keys.
  const plain = 'Risk-defined short premium; desk-wide BH; ask-side marks; sk-12 is not a key; Bearer is a word.\n';
  assert.equal(desk.admitDoc({ path, content: plain }, e).path, path);
  // A short configured value is not looked for (it would match ordinary text).
  assert.equal(desk.admitDoc({ path, content: 'abc short' }, { ...e, SAIL_API_KEY: 'abc' }).path, path);
});

test('git\'s blob id is computed as git computes it', () => {
  assert.equal(desk.blobSha('hello\n'), 'ce013625030ba8dba906f756967f9e9ca394464a');
  assert.equal(desk.blobSha(''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391');
});

test('a new page is committed to main with its desk: message; a changed page replaces its blob; the same page again commits nothing', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  const path = 'docs/runs/desk/2026-10-05.md';
  const first = await call(post({ path, content: PAGE, message: 'scoreboard' }), { gate, hub });
  assert.equal(first.response.status, 200, JSON.stringify(first.body));
  assert.deepEqual(first.body, { ok: true, committed: true, path, commit: hub.commits[0].commit, docs_today: 1 });
  const [put] = puts(hub);
  assert.equal(put.url, `https://api.github.com/repos/${GITHUB_REPO}/contents/${path}`);
  assert.deepEqual(Object.keys(put.body).sort(), ['branch', 'content', 'message']);
  assert.equal(put.body.branch, 'main');
  assert.equal(put.body.message, `desk: scoreboard\n\n${desk.FOOTER}`);
  assert.equal(Buffer.from(put.body.content, 'base64').toString('utf8'), PAGE);
  assert.equal(put.headers.Authorization, `Bearer ${GITHUB_TOKEN}`);
  assert.equal(put.redirect, 'manual');

  const changed = await call(post({ path, content: `${PAGE}Missed: 0.\n` }), { gate, hub });
  assert.equal(changed.response.status, 200);
  assert.equal(puts(hub)[1].body.sha, desk.blobSha(PAGE), 'the blob it replaces');
  assert.equal(hub.contents.get(path), `${PAGE}Missed: 0.\n`);

  const same = await call(post({ path, content: `${PAGE}Missed: 0.\n` }), { gate, hub });
  assert.deepEqual(same.body, { ok: true, committed: false, unchanged: true, path });
  assert.equal(puts(hub).length, 2, 'no commit');
  assert.equal(gate.status(NOW).autonomy.docs.commits, 2, 'and no place taken');
  assert.equal(gate.status(NOW).autonomy.docs.recent[0].outcome, 'committed');
});

test('six docs commits a New York day; a refused or unchanged post takes no place; then 429 until New York\'s midnight', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  for (let n = 1; n <= 6; n += 1) {
    const answer = await call(post({ path: `docs/runs/desk/2026-10-05-page-${n}.md`, content: `page ${n}\n` }), { gate, hub });
    assert.equal(answer.response.status, 200, `page ${n}`);
    // A bad post between them costs nothing.
    assert.equal((await call(post({ path: 'docs/design.md', content: 'x' }), { gate, hub })).response.status, 403);
  }
  const before = hub.calls.length;
  // 03:59Z the next UTC day is still Oct 5 in New York.
  const capped = await call(post({ path: 'docs/runs/desk/2026-10-05-page-7.md', content: 'page 7\n' }), { gate, hub, at: Date.parse('2026-10-06T03:59:00Z') });
  assert.equal(capped.response.status, 429);
  assert.equal(capped.body.cap, 'docs_day');
  assert.equal(capped.response.headers.get('Retry-After'), '3600');
  assert.equal(hub.calls.length, before, 'GitHub heard nothing');
  const tomorrow = await call(post({ path: 'docs/runs/desk/2026-10-06.md', content: 'page 7\n' }), { gate, hub, at: Date.parse('2026-10-06T04:01:00Z') });
  assert.equal(tomorrow.response.status, 200);
  assert.equal(tomorrow.body.docs_today, 1);
});

test('GitHub\'s no gives the place back; no answer keeps it; an unreadable main takes none; nothing echoes the token', async () => {
  const path = 'docs/runs/desk/2026-10-05.md';
  const gate = gateAt();
  const conflict = fakeHub({ script: key => (key.startsWith('PUT ') ? new Response(JSON.stringify({ message: `conflict ${GITHUB_TOKEN}` }), { status: 409 }) : undefined) });
  const refused = await call(post({ path, content: PAGE }), { gate, hub: conflict });
  assert.equal(refused.response.status, 409);
  assert.equal(refused.body.refused, 'github');
  assert.equal(JSON.stringify(refused.body).includes(GITHUB_TOKEN), false);
  assert.equal(gate.status(NOW).autonomy.docs.commits, 0);
  assert.equal(gate.status(NOW).autonomy.docs.recent[0].outcome, 'refused');

  const silent = fakeHub({ script: key => (key.startsWith('PUT ') ? Promise.reject(new Error('reset')) : undefined) });
  const lost = await call(post({ path, content: PAGE }), { gate, hub: silent });
  assert.equal(lost.response.status, 502);
  assert.equal(lost.body.refused, 'no_answer');
  assert.equal(gate.status(NOW).autonomy.docs.commits, 1, 'it may have committed');

  const down = fakeHub({ script: key => (key.startsWith('GET /contents') ? new Response('{}', { status: 500 }) : undefined) });
  assert.equal((await call(post({ path, content: PAGE }), { gate, hub: down })).response.status, 502);
  assert.equal(puts(down).length, 0);
  const folder = fakeHub({ script: key => (key.startsWith('GET /contents') ? new Response(JSON.stringify([{ name: 'x' }]), { status: 200 }) : undefined) });
  const odd = await call(post({ path, content: PAGE }), { gate, hub: folder });
  assert.equal(odd.response.status, 409);
  assert.equal(odd.body.refused, 'path');
  assert.equal(gate.status(NOW).autonomy.docs.commits, 1);
});

test('a 5xx on the commit is no answer: GitHub\'s edge may say so after the commit was made, so the place stays taken', async () => {
  const path = 'docs/runs/desk/2026-10-05.md';
  for (const status of [500, 502, 503, 504]) {
    const gate = gateAt();
    const hub = fakeHub({ script: key => (key.startsWith('PUT ') ? new Response(JSON.stringify({ message: 'Server Error' }), { status }) : undefined) });
    const lost = await call(post({ path, content: PAGE }), { gate, hub });
    assert.equal(lost.response.status, 502, String(status));
    assert.equal(lost.body.refused, 'no_answer', String(status));
    assert.equal(gate.status(NOW).autonomy.docs.commits, 1, `${status}: it may have committed`);
    assert.equal(gate.status(NOW).autonomy.docs.recent[0].outcome, 'unknown');
  }
  // A 4xx is GitHub's no, and gives the place back (422: the blob moved meanwhile).
  const gate = gateAt();
  const stale = fakeHub({ script: key => (key.startsWith('PUT ') ? new Response(JSON.stringify({ message: 'sha mismatch' }), { status: 422 }) : undefined) });
  assert.equal((await call(post({ path, content: PAGE }), { gate, hub: stale })).body.refused, 'github');
  assert.equal(gate.status(NOW).autonomy.docs.commits, 0);
});

test('the docs route is POST behind the runtime token, refuses a body it cannot read, and needs GitHub configured', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  assert.equal((await call(post({ path: 'docs/runs/desk/2026-10-05.md', content: PAGE }, 'wrong'), { gate, hub })).response.status, 401);
  assert.equal((await call(new Request(`${GATEWAY}/v1/github/docs`, { headers: { Authorization: `Bearer ${TOKEN}` } }), { gate, hub })).response.status, 405);
  assert.equal((await call(post('not json'), { gate, hub })).response.status, 400);
  assert.equal((await call(post({ path: 'docs/runs/desk/2026-10-05.md', content: 'x'.repeat(200 * 1024) }), { gate, hub })).response.status, 413);
  const bare = await route(post({ path: 'docs/runs/desk/2026-10-05.md', content: PAGE }), env({ GITHUB_REPO: '' }), { gate, fetcher: hub.fetcher, now: () => NOW });
  assert.equal(bare.status, 503);
  assert.equal(hub.calls.length, 0);
});
