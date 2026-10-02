// The engineer's contract with the gateway (V3-A integration review, lens "contract"): a proposal names the base it was
// written against and is refused when main changed any of its files since; the reviewer reads the exact diff at one
// head; a superseded engineer pull request can be closed; the kill switch stops merges; a stranger at the switch
// writes nothing to the Gate.

import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as github from '../lib/github.mjs';
import * as pulls from '../lib/pulls.mjs';
import { memoryStore, TOKEN, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';
import { fakeHub, enginePull, HEAD, OTHER } from './autonomy-fixtures.mjs';

const NOW = Date.parse('2026-10-05T16:00:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const env = () => ({ GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', GITHUB_REPO, GITHUB_TOKEN, CAP_TIMEZONE: 'America/New_York' });
const ask = (method, path, body, token = TOKEN) => new Request(GATEWAY + path, {
  method, headers: token ? { Authorization: `Bearer ${token}` } : {}, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});
const call = async (request, { gate, hub }) => {
  const response = await route(request, env(), { gate, fetcher: hub.fetcher, now: () => NOW });
  return { response, body: await response.clone().json().catch(() => null) };
};
const gateAt = () => createGate({ store: memoryStore(), env: env(), now: () => NOW });
const sha1 = text => createHash('sha1').update(text).digest('hex');
const reply = (status, data) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

const RESEARCHER = 'league/swarm/researcher.py';
const PREFLIGHT = 'league/swarm/preflight.py';

/**
 * A git small enough to read the way the base check reads it: nested trees (`GET /git/trees/<sha>` lists one
 * directory), commits, main's ref, and the writes a proposal makes. `land(files)` puts a commit on main.
 */
function gitHub() {
  const calls = [];
  const dirs = new Map();     // tree sha -> [{ path, type, sha }]
  const commits = new Map();  // commit sha -> root tree sha
  const refs = new Map();
  const plant = (files, prefix = '') => {
    const here = new Map();
    for (const [path, text] of Object.entries(files)) {
      if (!path.startsWith(prefix)) continue;
      const rest = path.slice(prefix.length);
      const [head, ...tail] = rest.split('/');
      if (tail.length) here.set(head, { path: head, type: 'tree', sha: plant(files, `${prefix}${head}/`) });
      else here.set(head, { path: head, type: 'blob', sha: sha1(`blob ${text}`) });
    }
    const listing = [...here.values()].sort((a, b) => (a.path < b.path ? -1 : 1));
    const sha = sha1(JSON.stringify(listing));
    dirs.set(sha, listing);
    return sha;
  };
  let main = { [RESEARCHER]: 'researcher v1\n', [PREFLIGHT]: 'preflight v1\n', 'README.md': 'readme\n' };
  const commit = files => {
    const sha = sha1(`commit ${commits.size} ${JSON.stringify(files)}`);
    commits.set(sha, plant(files));
    return sha;
  };
  refs.set('main', commit(main));
  const state = {
    calls, refs,
    land(changes) { main = { ...main, ...changes }; refs.set('main', commit(main)); return refs.get('main'); },
  };
  state.fetcher = async (url, init = {}) => {
    const path = String(url).slice(`https://api.github.com/repos/${GITHUB_REPO}`.length);
    const key = `${init.method} ${path}`;
    const body = init.body === undefined ? undefined : JSON.parse(init.body);
    calls.push({ key, method: init.method, body });
    let match;
    if ((match = /^GET \/git\/ref\/heads\/(.+)$/.exec(key))) {
      return refs.has(match[1]) ? reply(200, { object: { sha: refs.get(match[1]) } }) : reply(404, { message: 'Not Found' });
    }
    if ((match = /^GET \/git\/commits\/([0-9a-f]+)$/.exec(key))) {
      return commits.has(match[1]) ? reply(200, { sha: match[1], tree: { sha: commits.get(match[1]) } }) : reply(422, { message: 'No commit found' });
    }
    if ((match = /^GET \/git\/trees\/([0-9a-f]+)$/.exec(key))) {
      return dirs.has(match[1]) ? reply(200, { sha: match[1], truncated: false, tree: dirs.get(match[1]) }) : reply(404, { message: 'Not Found' });
    }
    if (key === 'POST /git/blobs') return reply(201, { sha: sha1(`blob ${body.content}`) });
    if (key === 'POST /git/trees') return reply(201, { sha: sha1(JSON.stringify(body)) });
    if (key === 'POST /git/commits') return reply(201, { sha: sha1(`new ${JSON.stringify(body)}`) });
    if (key === 'POST /git/refs') { refs.set(body.ref.replace('refs/heads/', ''), body.sha); return reply(201, { object: { sha: body.sha } }); }
    if (key === 'POST /pulls') { state.opened = body; return reply(201, { number: 91, html_url: 'https://github.com/x/pull/91' }); }
    return reply(404, { message: `unscripted: ${key}` });
  };
  return state;
}

const proposal = (base, files = [{ path: RESEARCHER, content: 'researcher v2\n' }]) =>
  github.admit({ role: 'engineer', lane: 'research', slug: 'research-sweep', title: 'Sweeps by default', body: 'Measured.', base_sha: base, files });
const open = (hub, admitted) => github.openPullRequest({ repo: GITHUB_REPO, token: GITHUB_TOKEN, proposal: admitted, fetcher: hub.fetcher });
const posts = hub => hub.calls.filter(made => made.method !== 'GET').map(made => made.key);

test('an engineer proposal must name its base commit; no other role names one', () => {
  const missing = github.admit({ role: 'engineer', lane: 'research', slug: 'research-sweep', title: 't', files: [{ path: RESEARCHER, content: 'x' }] });
  assert.equal(missing.status, 400);
  assert.match(missing.error, /base_sha/);
  assert.equal(proposal('main').status, 400, 'a branch name is not a commit');
  assert.equal(proposal(HEAD.toUpperCase()).status, 400);
  assert.equal(proposal(HEAD).base, HEAD);
  const other = github.admit({ role: 'architect', slug: 'x1', title: 't', base_sha: HEAD, files: [{ path: 'league/strategies/x.py', content: '' }] });
  assert.equal(other.status, 400);
});

test('a proposal on main\'s own head opens, and its pull request records the base', async () => {
  const hub = gitHub();
  const base = hub.refs.get('main');
  const opened = await open(hub, proposal(base));
  assert.equal(opened.ok, true, JSON.stringify(opened));
  assert.ok(hub.opened.body.includes(`Base: ${base}`));
  assert.equal(hub.calls.filter(made => made.key.startsWith('GET /git/trees/')).length, 0, 'the same commit needs no tree read');
});

test('main moving elsewhere does not refuse a proposal; main changing one of its files does, before anything is written', async () => {
  const hub = gitHub();
  const base = hub.refs.get('main');
  hub.land({ 'league/swarm/loop.py': 'a new file elsewhere\n', 'README.md': 'readme v2\n' });
  const elsewhere = await open(hub, proposal(base));
  assert.equal(elsewhere.ok, true, JSON.stringify(elsewhere));

  const fresh = gitHub();
  const old = fresh.refs.get('main');
  fresh.land({ [RESEARCHER]: 'researcher v1 with the owner\'s fix\n' });
  const moved = await open(fresh, proposal(old, [{ path: PREFLIGHT, content: 'preflight v2\n' }, { path: RESEARCHER, content: 'researcher v2\n' }]));
  assert.equal(moved.status, 409);
  assert.equal(moved.refused, 'base_moved');
  assert.match(moved.error, /league\/swarm\/researcher\.py/);
  assert.doesNotMatch(moved.error, /preflight/);
  assert.equal(moved.created, false, 'a refused base takes no place of the day');
  assert.deepEqual(posts(fresh), [], 'nothing is written to GitHub');

  // A new file the base did not have, that main has since added, is a change on main too.
  const added = gitHub();
  const before = added.refs.get('main');
  added.land({ 'league/tests/test_harness_candidate_sweep.py': 'def test_x(): pass\n' });
  const clash = await open(added, proposal(before, [{ path: 'league/tests/test_harness_candidate_sweep.py', content: 'def test_y(): pass\n' }]));
  assert.equal(clash.refused, 'base_moved');
});

test('a base GitHub does not know is refused', async () => {
  const hub = gitHub();
  hub.land({ README: 'x' });
  const unknown = await open(hub, proposal('c'.repeat(40)));
  assert.equal(unknown.status, 409);
  assert.equal(unknown.refused, 'base_unknown');
  assert.deepEqual(posts(hub), []);
});

test('an engineer proposal that reached openPullRequest with no base is refused (the check cannot be skipped)', async () => {
  const hub = gitHub();
  const admitted = proposal(hub.refs.get('main'));
  delete admitted.base;
  const refused = await open(hub, admitted);
  assert.equal(refused.status, 400);
  assert.equal(refused.refused, 'base_missing');
});

// ------------------------------------------------------------------------------------------- the reviewer's diff

const patchHub = () => {
  const hub = fakeHub();
  hub.files.set(77, [
    { filename: RESEARCHER, status: 'modified', additions: 2, deletions: 1, changes: 3, patch: '@@ -1 +1,2 @@\n-a\n+b\n+c' },
    { filename: 'league/tests/test_harness_candidate_sweep.py', status: 'added', additions: 1, deletions: 0, changes: 1, patch: '@@ -0,0 +1 @@\n+x' },
  ]);
  return hub;
};

test('the reviewer reads the exact diff at one head, whole, behind the gateway token', async () => {
  const hub = patchHub();
  const gate = gateAt();
  const read = await call(ask('GET', `/v1/github/pr/77/files?head_sha=${HEAD}`), { gate, hub });
  assert.equal(read.response.status, 200, JSON.stringify(read.body));
  assert.equal(read.body.complete, true);
  assert.equal(read.body.head, HEAD);
  assert.deepEqual(read.body.files.map(file => [file.filename, file.patch_truncated]), [[RESEARCHER, false], ['league/tests/test_harness_candidate_sweep.py', false]]);
  assert.equal(read.body.files[0].patch, '@@ -1 +1,2 @@\n-a\n+b\n+c');
  assert.equal(JSON.stringify(read.body).includes(GITHUB_TOKEN), false);

  assert.equal((await call(ask('GET', `/v1/github/pr/77/files?head_sha=${OTHER}`), { gate, hub })).body.refused, 'head_moved');
  assert.equal((await call(ask('GET', '/v1/github/pr/77/files'), { gate, hub })).response.status, 400);
  assert.equal((await call(ask('GET', `/v1/github/pr/78/files?head_sha=${HEAD}`), { gate, hub })).response.status, 404);
  assert.equal((await call(ask('POST', `/v1/github/pr/77/files?head_sha=${HEAD}`, {}), { gate, hub })).response.status, 405);
  assert.equal((await call(ask('GET', `/v1/github/pr/77/files?head_sha=${HEAD}`, undefined, 'wrong'), { gate, hub })).response.status, 401);
  assert.equal(hub.calls.filter(made => made.method !== 'GET').length, 0, 'a read writes nothing');
});

test('a diff GitHub left out or one cut short is never complete', async () => {
  const hub = patchHub();
  hub.files.get(77)[0].patch = undefined;
  const missing = await pulls.pullFiles({ repo: GITHUB_REPO, token: GITHUB_TOKEN, number: 77, headSha: HEAD, fetcher: hub.fetcher });
  assert.equal(missing.complete, false);
  const long = patchHub();
  long.files.get(77)[0].patch = 'x'.repeat(pulls.MAX_PATCH_CHARS + 5);
  const cut = await pulls.pullFiles({ repo: GITHUB_REPO, token: GITHUB_TOKEN, number: 77, headSha: HEAD, fetcher: long.fetcher });
  assert.equal(cut.complete, false);
  assert.equal(cut.files[0].patch_truncated, true);
  assert.equal(cut.files[0].patch.length, pulls.MAX_PATCH_CHARS);
});

// ------------------------------------------------------------------------------------------------------ the close

const closingHub = (pull = enginePull()) => {
  const hub = fakeHub({
    script: key => {
      if (key === 'PATCH /pulls/77') { hub.pulls.get(77).state = 'closed'; return reply(200, { number: 77, state: 'closed' }); }
      return undefined;
    },
  });
  hub.pulls.set(77, pull);
  return hub;
};

test('an engineer pull request closes at its exact head; nothing else closes here', async () => {
  const gate = gateAt();
  const hub = closingHub();
  const closed = await call(ask('POST', '/v1/github/close', { pr: 77, head_sha: HEAD }), { gate, hub });
  assert.equal(closed.response.status, 200, JSON.stringify(closed.body));
  assert.deepEqual(closed.body, { ok: true, closed: true, pr: 77, head_sha: HEAD });
  assert.deepEqual(hub.calls.filter(made => made.method !== 'GET').map(made => [made.key, made.body]), [['PATCH /pulls/77', { state: 'closed' }]]);

  const moved = closingHub();
  assert.equal((await call(ask('POST', '/v1/github/close', { pr: 77, head_sha: OTHER }), { gate, hub: moved })).body.refused, 'head_moved');
  const owners = closingHub(enginePull({ head: { ref: 'merton/architect/x1-1a2b3c4d', sha: HEAD, repo: { full_name: GITHUB_REPO } } }));
  const refused = await call(ask('POST', '/v1/github/close', { pr: 77, head_sha: HEAD }), { gate, hub: owners });
  assert.equal(refused.response.status, 403);
  assert.equal(refused.body.refused, 'branch');
  for (const hubbed of [moved, owners]) assert.equal(hubbed.calls.filter(made => made.method !== 'GET').length, 0);
  assert.equal((await call(ask('GET', '/v1/github/close'), { gate, hub })).response.status, 405);
});

// ----------------------------------------------------------------------------------------- the kill switch, the log

test('the kill switch stops the merge (a merge is a deploy); the review still records', async () => {
  const gate = gateAt();
  const hub = fakeHub();
  gate.setKill(true, NOW);
  const reviewed = await call(ask('POST', '/v1/github/review', { pr: 77, head_sha: HEAD, verdict: 'approve', reasons: ['fine'] }), { gate, hub });
  assert.equal(reviewed.response.status, 200, JSON.stringify(reviewed.body));
  const merged = await call(ask('POST', '/v1/github/merge', { pr: 77, head_sha: HEAD }), { gate, hub });
  assert.equal(merged.response.status, 423, JSON.stringify(merged.body));
  assert.equal(merged.body.cap, 'kill_switch');
  assert.deepEqual(hub.merged, []);
  assert.equal(gate.mergesToday(NOW), 0, 'a refused merge takes no place');
  gate.setKill(false, NOW);
  assert.equal((await call(ask('POST', '/v1/github/merge', { pr: 77, head_sha: HEAD }), { gate, hub })).body.merged, true);
});

test('a stranger at the switch writes nothing to the Gate', async () => {
  const gate = gateAt();
  const hub = fakeHub();
  let written = 0;
  const record = gate.adminRecord.bind(gate);
  gate.adminRecord = entry => { written += 1; return record(entry); };
  for (const token of [null, 'wrong']) {
    for (const path of ['/v1/kill', '/v1/unkill']) assert.equal((await call(ask('POST', path, undefined, token), { gate, hub })).response.status, 401);
  }
  assert.equal(written, 0);
  await call(ask('POST', '/v1/unkill', undefined, TOKEN), { gate, hub });
  assert.equal(written, 1, 'the runtime token at the owner\'s release is still logged');
});
