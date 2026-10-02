// The engineer's pull requests (LTCM v3, V3-A, WP8b): its lanes and their mirror of league/ci.py, what a proposal of
// each lane may write, the engineer's own file and request ceilings, and its own New York day of pull requests, apart
// from the other roles' day. The merge route's lane wall is test/merge.test.mjs's.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as github from '../lib/github.mjs';
import { protectedRefusal } from '../lib/protected.mjs';
import { fakeGitHub, memoryStore, TOKEN, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-05T16:00:00Z');  // noon in New York, a Monday
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const env = (extra = {}) => ({ GATEWAY_TOKEN: TOKEN, GITHUB_REPO, GITHUB_TOKEN, CAP_TIMEZONE: 'America/New_York', ...extra });
const gateAt = (settings = {}) => createGate({ store: memoryStore(), env: env(settings), now: () => NOW });
const send = async (body, { gate, hub, at = NOW, settings = {} }) => {
  const request = new Request(`${GATEWAY}/v1/github/pr`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: typeof body === 'string' ? body : JSON.stringify(body),
  });
  const response = await route(request, env(settings), { gate, fetcher: hub.fetcher, now: () => at });
  return { response, body: await response.clone().json().catch(() => null) };
};

const SURFACES = {
  scheduler: ['league/swarm/loop.py'],
  research: ['league/swarm/researcher.py', 'league/swarm/preflight.py', 'league/swarm/claude_research.py'],
  memory: ['league/swarm/architect.py', 'league/swarm/strategist.py', 'league/swarm/diagnostician.py', 'league/swarm/seeds.py', 'league/swarm/mechanisms.py'],
  data: ['league/sailbox.py', 'league/data_job.py'],
};
const engineer = (extra = {}) => ({
  role: 'engineer', lane: 'research', slug: 'preflight-reads', title: 'Faster preflight reads',
  body: 'The lane metric, the predicted effect and the canary plan.',
  files: [{ path: 'league/swarm/preflight.py', content: 'FAST = True\n' }, { path: 'league/tests/test_harness_candidate_preflight.py', content: 'X = 1\n' }],
  ...extra,
});
const ARCHITECT = {
  role: 'architect', slug: 'kalshi-weather-favorites', title: 'Add a strategy',
  files: [{ path: 'league/strategies/kalshi_weather_favorites.py', content: 'EDGE = 0.04\n' }],
};

// ------------------------------------------------------------------------------------------------------- the lanes

test('the engineer s lanes are league/ci.py s, none of their paths is protected, and no other role may write them', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(github.ENGINEER_LANES)), SURFACES);
  assert.ok(Object.isFrozen(github.ENGINEER_LANES) && Object.values(github.ENGINEER_LANES).every(Object.isFrozen));
  // league/ci.py judges engineer branches by its own copy of the table: the two must be one list.
  const source = readFileSync(new URL('../../league/ci.py', import.meta.url), 'utf8');
  const block = /ENGINEER_LANES: dict\[str, tuple\[str, \.\.\.\]\] = \{([\s\S]*?)\n\}/.exec(source);
  assert.ok(block, 'league/ci.py declares ENGINEER_LANES');
  const lanes = Object.fromEntries([...block[1].matchAll(/"([a-z]+)":\s*\(([^)]*)\)/g)]
    .map(([, lane, paths]) => [lane, [...paths.matchAll(/"([^"]+)"/g)].map(match => match[1])]));
  assert.deepEqual(lanes, SURFACES, 'league/ci.py ENGINEER_LANES and github.ENGINEER_LANES are the same table');
  assert.equal(/ENGINEER_TESTS = "([^"]+)"/.exec(source)?.[1], github.ENGINEER_TEST_GLOB);
  for (const path of Object.values(SURFACES).flat()) {
    assert.equal(protectedRefusal(path), null, path);
    for (const role of ['architect', 'toolsmith', 'operator', 'designer', 'teacher']) assert.notEqual(github.pathRefusal(role, path), null, `${role} ${path}`);
  }
});

test('the new-test glob is one name of a-z, 0-9 and _ under league/tests, ending .py, and nothing else', () => {
  for (const path of ['league/tests/test_harness_candidate_preflight.py', 'league/tests/test_harness_candidate_x.py',
    'league/tests/test_harness_candidate_loop_2.py', 'league/tests/test_harness_candidate_0.py']) {
    assert.ok(github.ENGINEER_TEST.test(path), path);
    for (const lane of Object.keys(SURFACES)) assert.equal(github.laneRefusal(lane, path), null, `${lane} ${path}`);
  }
  for (const path of ['league/tests/test_harness_candidate_.py', 'league/tests/test_harness_candidate_x.pyc',
    'league/tests/test_harness_candidate_x.py.bak', 'league/tests/test_harness_candidate_x/y.py', 'league/tests/test_harness_candidate_X.py',
    'league/tests/test_harness_candidate_a-b.py', 'league/tests/sub/test_harness_candidate_x.py', 'league/tests/test_harness_x.py',
    'League/tests/test_harness_candidate_x.py', 'league/tests/test_swarm_loop.py', 'league/tests/test_tool_x.py']) {
    assert.equal(github.ENGINEER_TEST.test(path), false, path);
    assert.match(github.laneRefusal('research', path), /outside the research lane/, path);
  }
});

test('the engineer s proposal names a known lane and writes only that lane s surface and new tests', () => {
  for (const [lane, own] of Object.entries(SURFACES)) {
    for (const path of own) {
      assert.equal(github.pathRefusal('engineer', path, github.ROLES, lane), null, `${lane} ${path}`);
      const admitted = github.admit(engineer({ lane, files: [{ path, content: 'X = 1\n' }] }));
      assert.equal(admitted.error, undefined, `${lane} ${path}`);
      assert.equal(admitted.lane, lane);
      // Every other lane's surface is refused to this lane.
      for (const other of Object.keys(SURFACES).filter(name => name !== lane)) {
        const refused = github.admit(engineer({ lane: other, files: [{ path, content: 'X = 1\n' }] }));
        assert.equal(refused.status, 403, `${other} may not write ${path}`);
        assert.match(refused.error, new RegExp(`is refused: outside the ${other} lane`));
        assert.equal(refused.path, path);
      }
    }
  }
  // Research-class paths outside every lane, and the protected and judged paths, are refused to every lane.
  for (const path of ['league/ops/agenda.py', 'league/swarm/models.py', 'league/house.py', 'league/swarm/loop_v2.py',
    'League/Swarm/Loop.py', 'league/swarm/harness_lanes.py', 'scripts/data/boxlib.py', 'league/tests/test_swarm_loop.py']) {
    for (const lane of Object.keys(SURFACES)) assert.equal(github.admit(engineer({ lane, files: [{ path, content: '' }] })).status, 403, `${lane} ${path}`);
  }
  for (const path of ['league/ci.py', 'league/swarm/bands.py', 'league/ops/budget.py', 'league/live/step.py', 'gateway/lib/github.mjs',
    '.github/workflows/checks.yml', 'league/config.json', 'league/swarm/.gitattributes', 'league/swarm/../ci.py']) {
    for (const lane of Object.keys(SURFACES)) {
      assert.match(github.pathRefusal('engineer', path, github.ROLES, lane), /no role may write|no automated change may write|git's own files|normalized/, `${lane} ${path}`);
    }
  }
  // No lane, an unknown one, one inherited from Object, or a lane on another role's proposal: refused by shape.
  for (const bad of [{ lane: undefined }, { lane: null }, { lane: 'execution' }, { lane: 'Research' }, { lane: 'constructor' },
    { lane: 'toString' }, { lane: ['research'] }]) {
    const refused = github.admit(engineer(bad));
    assert.equal(refused.status, 400, JSON.stringify(bad));
    assert.match(refused.error, /The lane must be one of: scheduler, research, memory, data\./);
  }
  assert.equal(github.pathRefusal('engineer', 'league/swarm/loop.py'), 'the lane is unknown', 'without its lane the engineer writes nothing');
  for (const lane of ['research', null, '']) {
    const refused = github.admit({ ...ARCHITECT, lane });
    assert.equal(refused.status, 400);
    assert.equal(refused.error, 'Only the engineer names a lane.');
  }
  assert.equal(github.admit(ARCHITECT).lane, undefined, 'another role s proposal carries no lane');
});

test('the engineer s branch is engineer/<lane>/<slug>-<8 hex>, named from the files, and its lane reads back from it', () => {
  const admitted = github.admit(engineer());
  const canonical = JSON.stringify(github.canonicalFiles(engineer().files).map(file => [file.path, file.content]));
  const hash = createHash('sha256').update(canonical).digest('hex').slice(0, 8);
  assert.equal(admitted.branch, `engineer/research/preflight-reads-${hash}`);
  assert.equal(github.admit(engineer({ files: [...engineer().files].reverse(), title: 'Other words' })).branch, admitted.branch, 'a retry is the same branch');
  const tests = [{ path: 'league/tests/test_harness_candidate_x.py', content: 'X = 1\n' }];
  assert.equal(github.admit(engineer({ lane: 'memory', files: tests })).branch.split('/').slice(0, 2).join('/'), 'engineer/memory');
  for (const lane of Object.keys(SURFACES)) assert.equal(github.engineerLane(`engineer/${lane}/a-thing-0123abcd`), lane);
  for (const ref of ['engineer/a-thing-0123abcd', 'engineer/execution/a-thing-0123abcd', 'engineer/research/a-thing', 'engineer/research/a-thing-0123ABCD',
    'engineer/research/a/thing-0123abcd', 'engineer/research/-thing-0123abcd', 'merton/engineer/research/a-thing-0123abcd', 'engineer/constructor/a-thing-0123abcd',
    'engineer/research/a-thing-0123abcd\n', '', null, 7]) {
    assert.equal(github.engineerLane(ref), null, JSON.stringify(ref));
  }
});

// ------------------------------------------------------------------------------------------------- the ceilings

test('the engineer carries at most six files of 512 KiB each; the other roles keep twelve of 64 KiB', () => {
  const tests = n => Array.from({ length: n }, (_, i) => ({ path: `league/tests/test_harness_candidate_t${i}.py`, content: `N = ${i}\n` }));
  assert.equal(github.admit(engineer({ files: tests(6) })).error, undefined, 'six files is the ceiling');
  assert.equal(github.admit(engineer({ files: tests(7) })).status, 400);
  assert.match(github.admit(engineer({ files: tests(7) })).error, /1 to 6 files/);
  const exactly = 'x'.repeat(512 * 1024);
  assert.equal(github.admit(engineer({ files: [{ path: 'league/swarm/researcher.py', content: exactly }] })).error, undefined, '512 KiB is the ceiling');
  assert.equal(github.admit(engineer({ files: [{ path: 'league/swarm/researcher.py', content: exactly + 'x' }] })).status, 400);
  assert.equal(github.admit(engineer({ files: [{ path: 'league/swarm/researcher.py', content: 'é'.repeat(256 * 1024 + 1) }] })).status, 400, 'bytes, not characters');
  // The other roles' ceilings are unchanged.
  assert.deepEqual(github.limitsFor('architect'), { files: 12, contentBytes: 64 * 1024, requestBytes: 256 * 1024 });
  assert.deepEqual(github.limitsFor('engineer'), { files: 6, contentBytes: 512 * 1024, requestBytes: 1536 * 1024 });
  assert.deepEqual(github.limitsFor(undefined), github.limitsFor('architect'));
  assert.equal(github.admit({ ...ARCHITECT, files: [{ ...ARCHITECT.files[0], content: 'x'.repeat(64 * 1024 + 1) }] }).status, 400);
  const twelve = Array.from({ length: 12 }, (_, n) => ({ path: `league/strategies/s${n}.py`, content: `N = ${n}\n` }));
  assert.equal(github.admit({ ...ARCHITECT, files: twelve }).error, undefined);
});

test('an engineer request of up to 1.5 MiB is read; over it, or another role s over 256 KiB, is a 413 GitHub never hears of', async () => {
  const big = n => 'x'.repeat(n * 1024);
  const hub = fakeGitHub();
  const gate = gateAt();
  // Three lane files of 500 KiB: a request of about 1.46 MiB, admitted and opened.
  const heavy = engineer({ files: SURFACES.research.map(path => ({ path, content: big(500) })) });
  assert.ok(Buffer.byteLength(JSON.stringify(heavy)) > 1400 * 1024 && Buffer.byteLength(JSON.stringify(heavy)) <= 1536 * 1024);
  const opened = await send(heavy, { gate, hub });
  assert.equal(opened.response.status, 200, JSON.stringify(opened.body));
  // Four of 400 KiB, each inside its own ceiling, are together over the request's 1.5 MiB.
  const before = hub.calls.length;
  const over = engineer({ files: [...SURFACES.research, 'league/tests/test_harness_candidate_x.py'].map(path => ({ path, content: big(400) })) });
  assert.equal((await send(over, { gate, hub })).response.status, 413);
  // The architect's request ceiling is what it was, though the route now reads further before it knows the role.
  const architect = { ...ARCHITECT, files: [0, 1, 2, 3, 4].map(n => ({ path: `league/strategies/heavy_${n}.py`, content: big(60) })) };
  assert.equal((await send(architect, { gate, hub })).response.status, 413);
  assert.equal((await send({ ...architect, role: 'janitor' }, { gate, hub })).response.status, 413, 'an unknown role has the smaller ceiling');
  assert.equal(hub.calls.length, before, 'GitHub heard none of it');
  assert.equal(gate.status(NOW).autonomy.engineer_pulls.count, 1);
  assert.equal(gate.status(NOW).github.pull_requests, 0);
});

// ------------------------------------------------------------------------------------------------------ the day

test('two engineer pull requests a New York day, apart from the other roles  day; a retry takes no place', async () => {
  const hub = fakeGitHub();
  const gate = gateAt({ GITHUB_MAX_PULLS_PER_DAY: '1' });
  const first = await send(engineer(), { gate, hub });
  assert.equal(first.response.status, 200, JSON.stringify(first.body));
  assert.deepEqual(Object.keys(first.body), ['ok', 'branch', 'number', 'url', 'head', 'lane']);
  assert.match(first.body.branch, /^engineer\/research\/preflight-reads-[0-9a-f]{8}$/);
  assert.equal(first.body.lane, 'research');
  assert.equal(hub.refs.get(first.body.branch), first.body.head);
  assert.equal(hub.calls.at(-1).key, 'POST /pulls');
  assert.equal(hub.calls.at(-1).body.head, first.body.branch);
  assert.match(hub.calls.at(-1).body.body, /Opened by Merton \(engineer\) through the LTCM gateway\.$/);
  assert.equal(JSON.stringify(first.body).includes(GITHUB_TOKEN), false);

  // The same proposal again is the same pull request, and its place is given back.
  const again = await send(engineer(), { gate, hub });
  assert.equal(again.response.status, 200);
  assert.equal(again.body.number, first.body.number);
  let health = gate.status(NOW).autonomy.engineer_pulls;
  assert.equal(health.count, 1);
  assert.equal(health.cap, 2);
  assert.deepEqual(health.recent.map(row => [row.outcome, row.pr, row.branch]),
    [['existing', first.body.number, first.body.branch], ['opened', first.body.number, first.body.branch]]);

  // The other roles' day is their own: one architect proposal fills it, and the engineer is not stopped by it.
  assert.equal((await send(ARCHITECT, { gate, hub })).response.status, 200);
  assert.equal((await send({ ...ARCHITECT, slug: 'another-one' }, { gate, hub })).response.status, 429);
  const second = await send(engineer({ lane: 'scheduler', slug: 'faster-loop', files: [{ path: 'league/swarm/loop.py', content: 'FAST = 1\n' }] }), { gate, hub });
  assert.equal(second.response.status, 200, JSON.stringify(second.body));
  assert.match(second.body.branch, /^engineer\/scheduler\/faster-loop-[0-9a-f]{8}$/);
  assert.equal(gate.status(NOW).github.pull_requests, 1, 'the engineer s pull requests are not the other roles  count');

  // The third is refused before GitHub hears of it, until New York's next day (04:00Z in October).
  const before = hub.calls.length;
  const third = engineer({ lane: 'data', slug: 'retry-data', files: [{ path: 'league/data_job.py', content: 'RETRY = 2\n' }] });
  const capped = await send(third, { gate, hub, at: Date.parse('2026-10-06T03:30:00Z') });
  assert.equal(capped.response.status, 429);
  assert.equal(capped.body.cap, 'engineer_day');
  assert.match(capped.body.error, /cap of 2 engineer pull requests/);
  assert.equal(capped.response.headers.get('Retry-After'), '3600');
  assert.equal(hub.calls.length, before, 'GitHub heard nothing');
  const tomorrow = await send(third, { gate, hub, at: Date.parse('2026-10-06T04:30:00Z') });
  assert.equal(tomorrow.response.status, 200);
  health = gate.status(Date.parse('2026-10-06T04:30:00Z')).autonomy.engineer_pulls;
  assert.equal(health.count, 1);
});

test('GitHub s no before a branch gives the engineer s place back; a branch nothing answered for keeps it', async () => {
  const gate = gateAt();
  const refusing = fakeGitHub({ script: key => (key === 'POST /git/blobs' ? new Response(JSON.stringify({ message: `nope ${GITHUB_TOKEN}` }), { status: 500 }) : undefined) });
  const refused = await send(engineer(), { gate, hub: refusing });
  assert.equal(refused.response.status, 502);
  assert.equal(JSON.stringify(refused.body).includes(GITHUB_TOKEN), false);
  let health = gate.status(NOW).autonomy.engineer_pulls;
  assert.equal(health.count, 0);
  assert.equal(health.recent[0].outcome, 'refused');

  const silent = fakeGitHub({ script: key => (key === 'POST /git/refs' ? Promise.reject(new Error('socket hang up')) : undefined) });
  const lost = await send(engineer(), { gate, hub: silent });
  assert.equal(lost.response.status, 502);
  health = gate.status(NOW).autonomy.engineer_pulls;
  assert.equal(health.count, 1, 'the branch may exist, so the place stays taken');
  assert.equal(health.recent[0].outcome, 'unknown');
  // A refused lane or shape takes no place at all.
  const wrong = await send(engineer({ files: [{ path: 'league/swarm/loop.py', content: '' }] }), { gate, hub: fakeGitHub() });
  assert.equal(wrong.response.status, 403);
  assert.equal(wrong.body.path, 'league/swarm/loop.py');
  assert.equal(gate.status(NOW).autonomy.engineer_pulls.count, 1);
});

test('the Durable Object exposes the engineer s pull request steps, each in one transaction, and the router awaits them', async () => {
  const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8');
  for (const name of ['engineerPullReserve', 'engineerPullSettle']) {
    assert.match(source, new RegExp(`\\b${name}\\(request\\) \\{ return this\\.ctx\\.storage\\.transactionSync\\(\\(\\) => this\\.gate\\.${name}\\(request\\)\\); \\}`), name);
  }
  const local = gateAt();
  const stub = Object.fromEntries(['engineerPullReserve', 'engineerPullSettle', 'status'].map(name => [name, async (...args) => local[name](...args)]));
  const hub = fakeGitHub();
  assert.equal((await send(engineer(), { gate: stub, hub })).response.status, 200);
  assert.equal((await send(engineer(), { gate: stub, hub })).response.status, 200);
  assert.equal(local.status(NOW).autonomy.engineer_pulls.count, 1);
});
