// The engineer's merges (V3-A, WP8): the protected paths and their mirror of league/ci.py, the engineer's branches,
// the review record, and every wall of POST /v1/github/merge, through the front door against a fake GitHub.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as github from '../lib/github.mjs';
import * as merge from '../lib/merge.mjs';
import { MERGE_FORBIDDEN, protectedRefusal } from '../lib/protected.mjs';
import { memoryStore, TOKEN, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';
import { fakeHub, enginePull, passedRun, passedJobs, HEAD, OTHER } from './autonomy-fixtures.mjs';

const NOW = Date.parse('2026-10-05T16:00:00Z');  // noon in New York, a Monday
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', GITHUB_REPO, GITHUB_TOKEN, CAP_TIMEZONE: 'America/New_York', ...extra,
});
const ask = (method, path, body, token = TOKEN) => new Request(GATEWAY + path, {
  method, headers: { Authorization: `Bearer ${token}` }, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});
const call = async (request, { gate, hub, at = NOW, settings = {} }) => {
  const response = await route(request, env(settings), { gate, fetcher: hub.fetcher, now: () => at });
  return { response, body: await response.clone().json().catch(() => null) };
};
const gateAt = () => createGate({ store: memoryStore(), env: env(), now: () => NOW });
const approve = (gate, hub, pr = 77, sha = HEAD, at = NOW) =>
  call(ask('POST', '/v1/github/review', { pr, head_sha: sha, verdict: 'approve', reasons: ['Isolated to the agenda reader; tests cover it.'] }), { gate, hub, at });
const mergeIt = (gate, hub, pr = 77, sha = HEAD, at = NOW) => call(ask('POST', '/v1/github/merge', { pr, head_sha: sha }), { gate, hub, at });
const writes = hub => hub.calls.filter(made => made.method !== 'GET');

// --------------------------------------------------------------------------------------------- the protected paths

test('the protected paths hold every entry of league/ci.py FORBIDDEN, WP1\'s protected jobs, and the evaluator\'s identity', () => {
  const source = readFileSync(new URL('../../league/ci.py', import.meta.url), 'utf8');
  const block = /FORBIDDEN: tuple\[str, \.\.\.\] = \(([\s\S]*?)\n\)/.exec(source);
  assert.ok(block, 'league/ci.py declares FORBIDDEN');
  const entries = [...block[1].replace(/#[^\n]*/g, '').matchAll(/"([^"]+)"/g)].map(match => match[1]);
  assert.ok(entries.length >= 30, `read ${entries.length} entries`);
  for (const entry of entries) assert.ok(MERGE_FORBIDDEN.includes(entry), `league/ci.py forbids ${entry}; the merge route must too`);
  for (const entry of ['league/ops/budget.py', 'league/ops/drills.py', 'league/ops/grant.py', 'league/live/', 'league/gym/',
    'league/swarm/gate.py', 'league/swarm/bands.py', 'league/swarm/evaluator.py', 'league/swarm/settings.py', 'league/swarm/store.py',
    'ltcm/data/', 'scripts/data/', '.github/', 'gateway/', 'deploy/', 'league/config.json', 'league/constitution.py']) {
    assert.ok(MERGE_FORBIDDEN.includes(entry), entry);
  }
  assert.ok(Object.isFrozen(MERGE_FORBIDDEN));
});

test('a protected path is refused by name, by tree and without case; a plain research-class path is not', () => {
  for (const path of ['league/constitution.py', 'League/Constitution.PY', 'league/live/step.py', 'league/gym/engine.py',
    'league/swarm/gate.py', 'league/swarm/settings.py', 'ltcm/data/us_equity_session.py', 'scripts/data/storelib.py',
    '.github/workflows/checks.yml', 'gateway/lib/merge.mjs', 'deploy/README.md', 'league/config.json', 'league/ops/grant.py',
    'league/updater.py', 'league/ci.py', 'league/live_trading.py']) {
    assert.match(protectedRefusal(path), /^protected \(/, path);
  }
  for (const path of ['/league/house.py', 'league/../league/ci.py', 'league//house.py', 'league/./house.py', 'league\\ci.py',
    'league/house.py\n', '', null, 7, 'x'.repeat(401)]) {
    assert.equal(protectedRefusal(path), 'not a plain repository path', JSON.stringify(path));
  }
  for (const path of ['.gitattributes', 'league/.gitignore', '.gitmodules']) assert.equal(protectedRefusal(path), 'git\'s own files');
  for (const path of ['league/house.py', 'league/ops/agenda.py', 'league/ops/runner.py', 'league/swarm/models.py',
    'league/swarm/settings_view.py', 'league/livery.py', 'docs/runs/desk/2026-10-05.md', 'league/tests/test_ops_agenda.py']) {
    assert.equal(protectedRefusal(path), null, path);
  }
});

test('the engineer opens engineer/ branches anywhere but the protected paths, through the proposal route', () => {
  assert.equal(github.pathRefusal('engineer', 'league/ops/agenda.py'), null);
  assert.equal(github.pathRefusal('engineer', 'league/swarm/models.py'), null);
  assert.match(github.pathRefusal('engineer', 'league/swarm/bands.py'), /no automated change may write this file: protected/);
  assert.match(github.pathRefusal('engineer', 'league/ops/budget.py'), /protected \(league\/ops\/budget\.py\)/);
  assert.match(github.pathRefusal('engineer', 'league/ledger.py'), /no role may write this file/);
  const admitted = github.admit({ role: 'engineer', slug: 'agenda-reads', title: 'Faster agenda reads', files: [{ path: 'league/ops/agenda.py', content: 'x = 1\n' }] });
  assert.match(admitted.branch, /^engineer\/agenda-reads-[0-9a-f]{8}$/);
  assert.equal(github.admit({ role: 'architect', slug: 'x1', title: 't', files: [{ path: 'league/strategies/x.py', content: '' }] }).branch.slice(0, 17), 'merton/architect/');
  const refused = github.admit({ role: 'engineer', slug: 'live-tweak', title: 't', files: [{ path: 'league/live/step.py', content: '' }] });
  assert.equal(refused.status, 403);
});

test('a review and a merge are read for their shape before anything is asked', () => {
  assert.deepEqual(merge.admitMerge({ pr: 77, head_sha: HEAD }), { pr: 77, head_sha: HEAD });
  for (const body of [null, [], { pr: 0, head_sha: HEAD }, { pr: '77', head_sha: HEAD }, { pr: 77, head_sha: HEAD.slice(1) },
    { pr: 77, head_sha: HEAD.toUpperCase() }, { pr: 1.5, head_sha: HEAD }]) {
    assert.equal(merge.admitMerge(body).status, 400, JSON.stringify(body));
  }
  assert.deepEqual(merge.admitReview({ pr: 77, head_sha: HEAD, verdict: 'reject', reasons: ' too broad ' }).reasons, ['too broad']);
  for (const extra of [{ verdict: 'lgtm' }, { reasons: [] }, { reasons: '' }, { reasons: ['ok', ''] }, { reasons: ['x'.repeat(1001)] },
    { reasons: Array.from({ length: 21 }, () => 'x') }, { reasons: [3] }]) {
    assert.equal(merge.admitReview({ pr: 77, head_sha: HEAD, verdict: 'approve', reasons: ['fine'], ...extra }).status, 400, JSON.stringify(extra));
  }
});

// ------------------------------------------------------------------------------------------------- the merge route

test('an approved engineer pull request with green checks merges by squash at exactly its head, and is counted', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  const reviewed = await approve(gate, hub);
  assert.equal(reviewed.response.status, 200, JSON.stringify(reviewed.body));
  assert.deepEqual(reviewed.body, { ok: true, pr: 77, head_sha: HEAD, verdict: 'approve', at: '2026-10-05T16:00:00.000Z' });
  assert.equal(writes(hub).length, 0, 'a review writes nothing to GitHub');

  const merged = await mergeIt(gate, hub);
  assert.equal(merged.response.status, 200, JSON.stringify(merged.body));
  assert.equal(merged.body.merged, true);
  assert.equal(merged.body.sha, hub.merged[0].merge_sha);
  assert.deepEqual(merged.body.ci, { run_id: 9001, jobs: ['gateway', 'tests (3.11)', 'tests (3.14)'] });
  assert.equal(merged.body.merges_today, 1);
  const [put] = writes(hub);
  assert.equal(put.key, 'PUT /pulls/77/merge');
  assert.equal(put.body.sha, HEAD, 'GitHub is told the exact commit');
  assert.equal(put.body.merge_method, 'squash');
  assert.equal(put.body.commit_title, 'Faster agenda reads (#77)');
  assert.match(put.body.commit_message, /checks\.yml run 9001 passed gateway, tests \(3\.11\), tests \(3\.14\) on a{40} and the automated review approved/);
  assert.equal(put.headers.Authorization, `Bearer ${GITHUB_TOKEN}`);
  assert.equal(JSON.stringify(merged.body).includes(GITHUB_TOKEN), false);
  // The order of the reads: the pull request, its files, its CI run, its jobs; then the merge.
  assert.deepEqual(hub.calls.map(made => made.key.split('?')[0]).slice(-5),
    ['GET /pulls/77', 'GET /pulls/77/files', 'GET /actions/workflows/checks.yml/runs', 'GET /actions/runs/9001/jobs', 'PUT /pulls/77/merge']);
  const health = gate.status(NOW).autonomy;
  assert.equal(health.merges.count, 1);
  assert.equal(health.merges.cap, 2);
  assert.deepEqual(health.merges.recent[0], { id: 1, at: '2026-10-05T16:00:00.000Z', pr: 77, sha: HEAD, outcome: 'merged', merge_sha: hub.merged[0].merge_sha });
  assert.deepEqual(health.reviews, { recorded: 1, approve: 1, reject: 0 });
});

test('no approve on the exact commit, or a reject of it, refuses the merge before GitHub hears of it', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  const none = await mergeIt(gate, hub);
  assert.equal(none.response.status, 409);
  assert.equal(none.body.refused, 'review_missing');
  assert.equal(hub.calls.length, 0);
  // An approve of another commit is not an approve of this one.
  hub.pulls.set(77, enginePull({ head: { ...enginePull().head, sha: OTHER } }));
  assert.equal((await approve(gate, hub, 77, OTHER)).response.status, 200);
  hub.pulls.set(77, enginePull());
  assert.equal((await mergeIt(gate, hub)).body.refused, 'review_missing');

  // A reject is final for its commit: an approve after it is refused, and the merge with it.
  const rejected = await call(ask('POST', '/v1/github/review', { pr: 77, head_sha: HEAD, verdict: 'reject', reasons: ['Changes the scheduler and the agenda at once.'] }), { gate, hub });
  assert.equal(rejected.response.status, 200);
  const late = await approve(gate, hub);
  assert.equal(late.response.status, 409);
  assert.equal(late.body.refused, 'review_rejected');
  const refused = await mergeIt(gate, hub);
  assert.equal(refused.body.refused, 'review_rejected');
  assert.equal(writes(hub).length, 0);
  // The same verdict twice is one record.
  const again = await call(ask('POST', '/v1/github/review', { pr: 77, head_sha: HEAD, verdict: 'reject', reasons: ['again'] }), { gate, hub });
  assert.equal(again.body.duplicate, true);
  assert.deepEqual(gate.status(NOW).autonomy.reviews, { recorded: 2, approve: 1, reject: 1 });
});

test('only an open engineer/ branch of this repository, aimed at main, at the named head, is reviewed or merged', async () => {
  const cases = [
    [{ head: { ...enginePull().head, ref: 'merton/architect/x-12345678' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, ref: 'engineer/' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, ref: 'feature/engineer/x' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, repo: { full_name: 'someone/long-term-capital-management' } } }, 403, 'fork'],
    [{ head: { ...enginePull().head, repo: null } }, 403, 'fork'],
    [{ base: { ref: 'release', repo: { full_name: GITHUB_REPO } } }, 403, 'base'],
    [{ base: { ref: 'main', repo: { full_name: 'someone/else' } } }, 403, 'base'],
    [{ head: { ...enginePull().head, sha: OTHER } }, 409, 'head_moved'],
    [{ state: 'closed' }, 409, 'not_open'],
    [{ merged: true }, 409, 'not_open'],
    [{ draft: true }, 409, 'draft'],
  ];
  for (const [extra, status, refused] of cases) {
    const hub = fakeHub();
    hub.pulls.set(77, enginePull(extra));
    const gate = gateAt();
    const review = await approve(gate, hub);
    assert.equal(review.response.status, status, `${refused} review`);
    assert.equal(review.body.refused, refused);
    // Even with an approve recorded for the commit, the merge refuses on the same rule.
    gate.reviewRecord({ pr: 77, sha: HEAD, verdict: 'approve', reasons: ['x'] });
    const merged = await mergeIt(gate, hub);
    assert.equal(merged.response.status, status, `${refused} merge`);
    assert.equal(merged.body.refused, refused);
    assert.equal(writes(hub).length, 0, refused);
    assert.equal(gate.status(NOW).autonomy.merges.count, 0);
  }
  const hub = fakeHub();
  const missing = await call(ask('POST', '/v1/github/review', { pr: 78, head_sha: HEAD, verdict: 'approve', reasons: ['x'] }), { gate: gateAt(), hub });
  assert.equal(missing.response.status, 404);
});

test('a pull request touching any protected path, by its name or its name before a rename, is never merged', async () => {
  for (const file of [
    { filename: 'league/constitution.py', status: 'modified' },
    { filename: 'league/live/step.py', status: 'removed' },
    { filename: 'League/Swarm/Bands.py', status: 'modified' },
    { filename: 'league/ops/agenda_v2.py', previous_filename: 'league/ops/budget.py', status: 'renamed' },
    { filename: '.github/workflows/checks.yml', status: 'modified' },
    { filename: 'gateway/lib/merge.mjs', status: 'modified' },
    { filename: 'league/config.json', status: 'modified' },
    { filename: '.gitattributes', status: 'added' },
    { filename: null, status: 'added' },
  ]) {
    const hub = fakeHub();
    hub.files.set(77, [{ filename: 'league/ops/agenda.py', status: 'modified' }, file]);
    const gate = gateAt();
    await approve(gate, hub);
    const refused = await mergeIt(gate, hub);
    assert.equal(refused.response.status, 403, JSON.stringify(file));
    assert.equal(refused.body.refused, 'protected_path');
    assert.equal(writes(hub).length, 0);
  }
});

test('the changed files are read whole, page by page, or the merge is refused', async () => {
  // 230 files over three pages, none protected: read whole, merged.
  const many = Array.from({ length: 230 }, (_, n) => ({ filename: `league/ops/lane_${n}.py`, status: 'added' }));
  let hub = fakeHub();
  hub.files.set(77, many);
  hub.pulls.set(77, enginePull({ changed_files: 230 }));
  let gate = gateAt();
  await approve(gate, hub);
  assert.equal((await mergeIt(gate, hub)).response.status, 200);
  assert.deepEqual(hub.calls.filter(made => made.key.startsWith('GET /pulls/77/files')).map(made => /&page=(\d+)$/.exec(made.key)[1]), ['1', '2', '3']);
  // A protected file on the third page is found.
  hub = fakeHub();
  hub.files.set(77, [...many.slice(0, 229), { filename: 'league/gym/engine.py', status: 'modified' }]);
  hub.pulls.set(77, enginePull({ changed_files: 230 }));
  gate = gateAt();
  await approve(gate, hub);
  assert.equal((await mergeIt(gate, hub)).body.refused, 'protected_path');
  // GitHub's list shorter than the pull request's own count; a count over 300; no count: refused.
  for (const [count, files, status] of [[3, many.slice(0, 2), 409], [301, many, 403], [undefined, many.slice(0, 2), 409], [0, [], 409]]) {
    hub = fakeHub();
    hub.files.set(77, files);
    hub.pulls.set(77, enginePull({ changed_files: count }));
    gate = gateAt();
    await approve(gate, hub);
    const refused = await mergeIt(gate, hub);
    assert.equal(refused.response.status, status, String(count));
    assert.equal(refused.body.refused, 'files');
    assert.equal(writes(hub).length, 0);
  }
});

test('checks.yml must have passed on exactly that commit: its latest run, with gateway, tests (3.11) and tests (3.14) green', async () => {
  const cases = [
    ['no run', hub => { hub.runs = []; }, 'ci_missing'],
    ['a run on another commit only', hub => { hub.runs = [passedRun(OTHER)]; }, 'ci_missing'],
    ['a run of a fork', hub => { hub.runs = [passedRun(HEAD, { head_repository: { full_name: 'someone/fork' } })]; }, 'ci_missing'],
    ['a run of another repository', hub => { hub.runs = [passedRun(HEAD, { repository: { full_name: 'someone/fork' } })]; }, 'ci_missing'],
    ['in progress', hub => { hub.runs = [passedRun(HEAD, { status: 'in_progress', conclusion: null })]; }, 'ci_pending'],
    ['failed', hub => { hub.runs = [passedRun(HEAD, { conclusion: 'failure' })]; }, 'ci_failed'],
    ['cancelled', hub => { hub.runs = [passedRun(HEAD, { conclusion: 'cancelled' })]; }, 'ci_failed'],
    ['a later re-run failed', hub => { hub.runs = [passedRun(), passedRun(HEAD, { id: 9002, created_at: '2026-10-05T15:00:00Z', conclusion: 'failure' })]; }, 'ci_failed'],
    ['a job missing', hub => { hub.jobs.set(9001, passedJobs().filter(job => job.name !== 'tests (3.14)')); }, 'ci_jobs'],
    ['a job failed', hub => { hub.jobs.set(9001, passedJobs().map(job => (job.name === 'gateway' ? { ...job, conclusion: 'failure' } : job))); }, 'ci_jobs'],
    ['a job skipped', hub => { hub.jobs.set(9001, passedJobs().map(job => (job.name === 'tests (3.11)' ? { ...job, conclusion: 'skipped' } : job))); }, 'ci_jobs'],
    ['a job named twice', hub => { hub.jobs.set(9001, [...passedJobs(), { id: 9, name: 'gateway', status: 'completed', conclusion: 'failure' }]); }, 'ci_jobs'],
  ];
  for (const [name, arrange, refused] of cases) {
    const hub = fakeHub();
    arrange(hub);
    const gate = gateAt();
    await approve(gate, hub);
    const answer = await mergeIt(gate, hub);
    assert.equal(answer.response.status, 409, name);
    assert.equal(answer.body.refused, refused, name);
    assert.equal(writes(hub).length, 0, name);
  }
  // An earlier failed run and a later passed one: the latest decides, and it passed.
  const hub = fakeHub();
  hub.runs = [passedRun(HEAD, { id: 8999, created_at: '2026-10-05T13:00:00Z', conclusion: 'failure' }), passedRun()];
  const gate = gateAt();
  await approve(gate, hub);
  assert.equal((await mergeIt(gate, hub)).response.status, 200);
});

test('two merges a New York day, then 429 before GitHub hears of it; the next New York day starts at zero', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  const shas = ['1', '2', '3'].map(digit => digit.repeat(40));
  for (const [n, sha] of shas.entries()) {
    const number = 80 + n;
    hub.pulls.set(number, enginePull({ number, head: { ...enginePull().head, sha } }));
    hub.files.set(number, [{ filename: 'league/ops/agenda.py', status: 'modified' }]);
    hub.pulls.get(number).changed_files = 1;
    hub.runs.push(passedRun(sha, { id: 9100 + n }));
    hub.jobs.set(9100 + n, passedJobs());
    await approve(gate, hub, number, sha);
  }
  assert.equal((await mergeIt(gate, hub, 80, shas[0])).response.status, 200);
  assert.equal((await mergeIt(gate, hub, 81, shas[1])).response.status, 200);
  const before = hub.calls.length;
  // 23:30 in New York is still the same day (03:30Z the next calendar day in UTC).
  const capped = await mergeIt(gate, hub, 82, shas[2], Date.parse('2026-10-06T03:30:00Z'));
  assert.equal(capped.response.status, 429);
  assert.equal(capped.body.cap, 'merge_day');
  assert.equal(capped.response.headers.get('Retry-After'), '3600');
  assert.equal(hub.calls.length, before, 'GitHub heard nothing');
  const tomorrow = await mergeIt(gate, hub, 82, shas[2], Date.parse('2026-10-06T04:30:00Z'));
  assert.equal(tomorrow.response.status, 200);
  assert.equal(tomorrow.body.merges_today, 1);
});

test('a merge GitHub refused gives its place back; a merge nothing answered keeps it, and says the outcome is unknown', async () => {
  // The head moved between the checks and the merge: GitHub's 409, nothing merged, the place given back.
  let moved = true;
  const hub = fakeHub({ script: key => (moved && key === 'PUT /pulls/77/merge'
    ? new Response(JSON.stringify({ message: `Head branch was modified ${GITHUB_TOKEN}` }), { status: 409 }) : undefined) });
  const gate = gateAt();
  await approve(gate, hub);
  const refused = await mergeIt(gate, hub);
  assert.equal(refused.response.status, 409);
  assert.equal(refused.body.refused, 'github');
  assert.equal(refused.body.merged, false);
  assert.equal(JSON.stringify(refused.body).includes(GITHUB_TOKEN), false, 'the token is never echoed');
  assert.equal(gate.status(NOW).autonomy.merges.count, 0);
  assert.equal(gate.status(NOW).autonomy.merges.recent[0].outcome, 'refused');
  // Nothing answered: the merge may have happened, so the place stays taken.
  moved = false;
  const silent = fakeHub({ script: key => (key === 'PUT /pulls/77/merge' ? Promise.reject(new Error('socket hang up')) : undefined) });
  const lost = await mergeIt(gate, silent);
  assert.equal(lost.response.status, 502);
  assert.equal(lost.body.merged, 'unknown');
  assert.equal(lost.body.refused, 'no_answer');
  assert.equal(gate.status(NOW).autonomy.merges.count, 1);
  assert.equal(gate.status(NOW).autonomy.merges.recent[0].outcome, 'unknown');
});

test('the merge and review routes are POST behind the runtime token, and need GitHub configured', async () => {
  const hub = fakeHub();
  for (const path of ['/v1/github/merge', '/v1/github/review']) {
    assert.equal((await call(ask('GET', path), { gate: gateAt(), hub })).response.status, 405, path);
    assert.equal((await call(ask('POST', path, { pr: 77, head_sha: HEAD }, 'wrong'), { gate: gateAt(), hub })).response.status, 401, path);
    assert.equal((await call(ask('POST', path, { pr: 77, head_sha: HEAD }, TOKEN + '-owner'), { gate: gateAt(), hub })).response.status, 401,
      `${path}: the owner's token opens no merge either`);
    const bare = await call(ask('POST', path, { pr: 77, head_sha: HEAD }), { gate: gateAt(), hub, settings: { GITHUB_TOKEN: '' } });
    assert.equal(bare.response.status, 503, path);
    const bad = await route(new Request(GATEWAY + path, { method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: 'not json' }), env(),
      { gate: gateAt(), fetcher: hub.fetcher, now: () => NOW });
    assert.equal(bad.status, 400, path);
  }
  assert.equal(hub.calls.length, 0);
});

test('the Durable Object exposes the merge, review and docs steps, each write in one transaction', () => {
  const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8');
  for (const name of ['mergeReserve', 'mergeSettle', 'reviewRecord', 'docsReserve', 'docsSettle', 'adminRecord']) {
    assert.match(source, new RegExp(`\\b${name}\\((request|entry)\\) \\{ return this\\.ctx\\.storage\\.transactionSync\\(\\(\\) => this\\.gate\\.${name}\\((request|entry)\\)\\); \\}`), name);
  }
  for (const name of ['mergesToday', 'docsToday', 'reviewFor']) assert.match(source, new RegExp(`\\b${name}\\(\\w+\\) \\{ return this\\.gate\\.${name}\\(`), name);
  assert.match(source, /setKill\(on, at, who\) \{ return this\.ctx\.storage\.transactionSync\(\(\) => this\.gate\.setKill\(on === true, at, who\)\); \}/);
});
