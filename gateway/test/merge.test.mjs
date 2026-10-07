// The engineer's merges (V3-A, WP8): the protected paths and their mirror of league/ci.py, the engineer's branches,
// the review record, and every wall of POST /v1/github/merge, through the front door against a fake GitHub.

import assert from 'node:assert/strict';
import test from 'node:test';
import { existsSync, readdirSync, readFileSync } from 'node:fs';

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
  call(ask('POST', '/v1/github/review', { pr, head_sha: sha, verdict: 'approve', reasons: ['Isolated to the preflight reader; tests cover it.'] }), { gate, hub, at });
const mergeIt = (gate, hub, pr = 77, sha = HEAD, at = NOW) => call(ask('POST', '/v1/github/merge', { pr, head_sha: sha }), { gate, hub, at });
const writes = hub => hub.calls.filter(made => made.method !== 'GET');

// --------------------------------------------------------------------------------------------- the protected paths

const repoText = rel => readFileSync(new URL(`../../${rel}`, import.meta.url), 'utf8');
const repoHas = rel => existsSync(new URL(`../../${rel}`, import.meta.url));
//: The quoted strings of a Python tuple assignment `NAME... = (...)` in `source` (comments dropped).
const pyTuple = (source, pattern) => {
  const block = pattern.exec(source);
  assert.ok(block, `${pattern} is declared`);
  return [...block[1].replace(/#[^\n]*/g, '').matchAll(/"([^"]+)"/g)].map(match => match[1]);
};
//: A tree entry is held when a file inside it is refused; a file entry when it is.
const held = entry => protectedRefusal(entry.endsWith('/') ? `${entry}x.py` : entry) !== null;

test('the protected paths hold every entry of league/ci.py FORBIDDEN, WP1\'s protected jobs, and the evaluator\'s identity', () => {
  const entries = pyTuple(repoText('league/ci.py'), /FORBIDDEN: tuple\[str, \.\.\.\] = \(([\s\S]*?)\n\)/);
  assert.ok(entries.length >= 30, `read ${entries.length} entries`);
  for (const entry of entries) assert.ok(MERGE_FORBIDDEN.includes(entry), `league/ci.py forbids ${entry}; the merge route must too`);
  for (const entry of ['league/ops/budget.py', 'league/ops/drills.py', 'league/ops/grant.py', 'league/live/', 'league/gym/',
    'league/swarm/gate.py', 'league/swarm/bands.py', 'league/swarm/evaluator.py', 'league/swarm/settings.py', 'league/swarm/store.py',
    'league/swarm/guard.py', 'league/swarm/models.py', 'league/ops/context.py', 'league/ops/economics.py',
    'ltcm/data/', 'scripts/data/', '.github/', 'gateway/', 'deploy/', 'league/config.json', 'league/constitution.py',
    'league/swarm/policy.json', 'league/ops/']) {
    assert.ok(MERGE_FORBIDDEN.includes(entry), entry);
  }
  assert.ok(Object.isFrozen(MERGE_FORBIDDEN));
});

test('what the Gym bundle, the evaluator fingerprint and the decider\'s sealed runtime carry is protected', () => {
  const sources = {
    'league/gym/driver.py LEAGUE_FILES': pyTuple(repoText('league/gym/driver.py'), /\nLEAGUE_FILES = \(([\s\S]*?)\)/),
    'league/swarm/harness_lanes.py LEAGUE_FILES': pyTuple(repoText('league/swarm/harness_lanes.py'), /\nLEAGUE_FILES = \(([\s\S]*?)\)/),
    'league/practice_runner.py RUNTIME_FILES': pyTuple(repoText('league/practice_runner.py'), /\nRUNTIME_FILES = \(([\s\S]*?)\n\)/),
    'league/practice_runner.py EXTRA_EVALUATOR_FILES': pyTuple(repoText('league/practice_runner.py'), /\nEXTRA_EVALUATOR_FILES = \(([\s\S]*?)\)/),
    'league/live/decider.py runtime files': pyTuple(repoText('league/live/decider.py'), /\n\s+files = \(("league\/__init__\.py"[\s\S]*?)\)/),
  };
  for (const [source, files] of Object.entries(sources)) {
    assert.ok(files.length >= 4, `${source}: read ${files.length}`);
    for (const file of files) assert.ok(held(file), `${source} carries ${file}; no automated merge may change it`);
  }
});

test('every module league/live/ and league/gym/ import from outside their trees is protected', () => {
  // `from ..x.y import a, b`, `from .. import a`, `from ltcm.x import a`, `import ltcm.x`, at any indentation.
  const importsOf = rel => {
    const text = repoText(rel);
    const pkg = rel.split('/').slice(0, -1);
    const found = [];
    for (const [, dots, module, names] of text.matchAll(/^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]+)/gm)) {
      const base = dots ? [...pkg.slice(0, pkg.length - (dots.length - 1)), ...(module ? module.split('.') : [])] : module.split('.');
      found.push(base);
      for (const name of names.replace(/[()]/g, '').split(',').map(part => part.trim().split(/\s+/)[0]).filter(Boolean)) found.push([...base, name]);
    }
    for (const [, module] of text.matchAll(/^[ \t]*import[ \t]+([\w.]+)/gm)) found.push(module.split('.'));
    return found.filter(parts => ['league', 'ltcm'].includes(parts[0]));
  };
  // Each package on the way and the module itself, as files of the repository.
  const filesOf = parts => parts.flatMap((_, i) => {
    const at = parts.slice(0, i + 1).join('/');
    return repoHas(`${at}/__init__.py`) ? [`${at}/__init__.py`] : repoHas(`${at}.py`) ? [`${at}.py`] : [];
  });
  const trees = ['league/live', 'league/gym'];
  const modules = trees.flatMap(tree => readdirSync(new URL(`../../${tree}/`, import.meta.url)).filter(name => name.endsWith('.py')).map(name => `${tree}/${name}`));
  assert.ok(modules.length >= 30, `read ${modules.length} modules`);
  // The Sail client ships the Gym bundle and reads the results back; it is in neither the bundle nor the fingerprint,
  // and it is the data lane's surface (league/swarm/harness_lanes.py), the one import the engineer may change.
  const transport = ['league/sailbox.py'];
  const outside = new Set();
  for (const rel of modules) {
    for (const file of importsOf(rel).flatMap(filesOf)) if (!trees.some(tree => file.startsWith(`${tree}/`))) outside.add(file);
  }
  for (const file of ['league/__init__.py', 'league/structure_core.py', 'ltcm/__init__.py', 'ltcm/performance.py', 'league/swarm/__init__.py']) {
    assert.ok(outside.has(file), `the import reader finds ${file}`);
  }
  for (const file of outside) {
    if (transport.includes(file)) continue;
    assert.ok(held(file), `league/live/ or league/gym/ imports ${file}; no automated merge may change it`);
  }
});

test('the harness loop\'s own protected paths are protected here, but the candidate\'s new test files', () => {
  const source = repoText('league/swarm/harness_lanes.py');
  const block = /\nPROTECTED: tuple\[tuple\[str, str\], \.\.\.\] = \(([\s\S]*?)\n\)/.exec(source);
  assert.ok(block);
  const patterns = [...block[1].replace(/#[^\n]*/g, '').matchAll(/\("([^"]+)", "[a-z]+"\)/g)].map(match => match[1]);
  assert.ok(patterns.length >= 50, `read ${patterns.length} patterns`);
  for (const pattern of patterns) {
    if (pattern === 'league/tests/*') continue;  // the engineer's surface holds its own new tests (ENGINEER_SURFACE.tests)
    const path = pattern.endsWith('/*') ? `${pattern.slice(0, -1)}x.py` : pattern;
    assert.ok(!pattern.slice(0, -1).includes('*'), pattern);
    assert.notEqual(protectedRefusal(path), null, `harness_lanes protects ${pattern}; so must the merge route`);
    for (const lane of Object.keys(github.ENGINEER_LANES)) assert.notEqual(github.pathRefusal('engineer', path, github.ROLES, lane), null, `${lane} ${pattern}`);
  }
});

test('the engineer\'s surface is the harness lanes\' surfaces, less the protected paths, and no wider', () => {
  const source = repoText('league/swarm/harness_lanes.py');
  const newTest = /\nNEW_TEST = "([^"]+)"/.exec(source)[1];
  assert.equal(newTest, 'league/tests/test_harness_candidate_*.py');
  const lanes = [...source.matchAll(/\n\s+surface=\(([\s\S]*?)\),\n/g)].map(match =>
    [...match[1].matchAll(/"([^"]+)"|NEW_TEST/g)].map(found => found[1] ?? newTest));
  assert.equal(lanes.length, 4, 'the research, memory, data and execution lanes');
  const surface = new Set(lanes.flat());
  assert.equal(newTest, github.ENGINEER_TEST_GLOB);
  assert.equal(github.ENGINEER_SURFACE.tests, github.ENGINEER_TEST);
  const laneOf = path => Object.keys(github.ENGINEER_LANES).find(lane => github.ENGINEER_LANES[lane].includes(path));
  for (const path of github.ENGINEER_SURFACE.only) {
    assert.ok(surface.has(path), `${path} is in no lane's surface`);
    assert.equal(protectedRefusal(path), null, path);
    assert.ok(laneOf(path), `${path} is in no lane of ENGINEER_LANES`);
    assert.equal(github.pathRefusal('engineer', path, github.ROLES, laneOf(path)), null, path);
    assert.ok(repoHas(path), `${path} exists`);
  }
  for (const path of surface) {
    if (path === newTest) continue;
    assert.ok(github.ENGINEER_SURFACE.only.includes(path) || github.ENGINEER_HELD.includes(path) || protectedRefusal(path) !== null,
      `the lanes' ${path} is neither in the engineer's surface, nor held, nor protected`);
  }
  // A held path is one the lanes declare and the lane table lists, unprotected, and never in the surface: it is held for
  // what the live path loads (ENGINEER_HELD), not for want of a declaration.
  for (const path of github.ENGINEER_HELD) {
    assert.ok(surface.has(path), path);
    assert.ok(laneOf(path), path);
    assert.equal(protectedRefusal(path), null, path);
    assert.equal(github.ENGINEER_SURFACE.only.includes(path), false, path);
    assert.ok(repoHas(path), `${path} exists`);
  }
  // The lane table (league/ci.py ENGINEER_LANES) is written no wider than the lanes declare: a path of its that no
  // harness lane's surface holds is refused to its own lane.
  const undeclared = [];
  for (const [lane, paths] of Object.entries(github.ENGINEER_LANES)) {
    for (const path of paths.filter(listed => !surface.has(listed))) {
      undeclared.push(path);
      assert.match(github.pathRefusal('engineer', path, github.ROLES, lane), /outside the engineer's lane surfaces/, `${lane} ${path}`);
    }
  }
  // The scheduler lane's file is one of them. The harness loop's own scheduler lane (league/swarm/improvement.py) is not
  // one of LANES and changes the Scheduler class's body alone (its patch_guard); the gateway reads no class, so the
  // whole file stays out of the surface.
  const scheduler = /\nSCHEDULER_PATH = "([^"]+)"/.exec(repoText('league/swarm/improvement.py'))?.[1];
  assert.equal(scheduler, 'league/swarm/loop.py');
  assert.deepEqual(github.ENGINEER_LANES.scheduler, [scheduler]);
  assert.deepEqual(undeclared, [scheduler, 'league/swarm/mechanisms.py']);
  assert.ok(Object.isFrozen(github.ENGINEER_SURFACE) && Object.isFrozen(github.ENGINEER_SURFACE.only));
});

test('a protected path is refused by name, by tree, by a file that would shadow it, and without case; a plain path is not', () => {
  for (const path of ['league/constitution.py', 'League/Constitution.PY', 'league/live/step.py', 'league/gym/engine.py',
    'league/swarm/gate.py', 'league/swarm/settings.py', 'ltcm/data/us_equity_session.py', 'scripts/data/storelib.py',
    '.github/workflows/checks.yml', 'gateway/lib/merge.mjs', 'deploy/README.md', 'league/config.json', 'league/ops/grant.py',
    'league/updater.py', 'league/ci.py', 'league/live_trading.py', 'league/structure_core.py', 'league/__init__.py',
    'league/structures.py', 'ltcm/__init__.py', 'ltcm/performance.py', 'league/swarm/policy.json', 'league/swarm/guard.py',
    'league/swarm/funding.py', 'league/ops/economics.py', 'league/ops/__init__.py', 'league/ops/registry.py',
    'league/swarm/harness_lanes.py', 'league/swarm/harness_judges/research.py', 'league/house.py', 'league/swarm/__init__.py']) {
    assert.match(protectedRefusal(path), /^protected \(/, path);
  }
  // A package, an extension module or bytecode of a protected module's name shadows it; so does a module of a
  // protected namespace package's name.
  for (const path of ['league/constitution/__init__.py', 'League/Constitution/__init__.py', 'league/swarm/gate/__init__.py',
    'league/updater/__init__.py', 'league/ci/__init__.py', 'league/structure_core/__init__.py',
    'league/constitution.cpython-311-x86_64-linux-gnu.so', 'league/swarm/bands.pyc', 'scripts/data.py', 'ltcm/data.py']) {
    assert.match(protectedRefusal(path), /^protected \(.*: a file that would shadow it\)$/, path);
  }
  for (const path of ['league/__pycache__/constitution.cpython-311.pyc', 'league/swarm/researcher.so', 'hook.pth',
    'league/sitecustomize.py', 'usercustomize.py', 'league/swarm/__pycache__/x.py', 'league/swarm/researcher.cpython-311.PYD']) {
    assert.equal(protectedRefusal(path), 'a file Python loads instead of source', path);
  }
  for (const path of ['/league/house.py', 'league/../league/ci.py', 'league//house.py', 'league/./house.py', 'league\\ci.py',
    'league/house.py\n', '', null, 7, 'x'.repeat(401)]) {
    assert.equal(protectedRefusal(path), 'not a plain repository path', JSON.stringify(path));
  }
  for (const path of ['.gitattributes', 'league/.gitignore', '.gitmodules']) assert.equal(protectedRefusal(path), 'git\'s own files');
  for (const path of ['league/swarm/researcher.py', 'league/sailbox.py', 'league/swarm/pool.py', 'league/swarm/settings_view.py', 'league/livery.py',
    'league/structures_view.py', 'docs/runs/desk/2026-10-05.md', 'league/tests/test_ops_agenda.py', 'league/gymnasium.py']) {
    assert.equal(protectedRefusal(path), null, path);
  }
});

test('the engineer opens engineer/<lane>/ branches inside its lane and never on a protected path (WP8b: test/engineer.test.mjs)', () => {
  assert.equal(github.pathRefusal('engineer', 'league/swarm/preflight.py', github.ROLES, 'research'), null);
  assert.match(github.pathRefusal('engineer', 'league/swarm/architect.py', github.ROLES, 'research'), /outside the research lane/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/loop.py', github.ROLES, 'research'), /outside the engineer's lane surfaces/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/pool.py', github.ROLES, 'research'), /outside the engineer's lane surfaces/);
  assert.match(github.pathRefusal('engineer', 'league/ops/agenda.py', github.ROLES, 'research'), /protected \(league\/ops\/\)/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/bands.py', github.ROLES, 'research'), /no automated change may write this file: protected/);
  assert.match(github.pathRefusal('engineer', 'league/ops/budget.py', github.ROLES, 'research'), /protected \(league\/ops\/budget\.py\)/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/models.py', github.ROLES, 'research'), /protected \(league\/swarm\/models\.py\)/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/guard.py', github.ROLES, 'research'), /protected \(league\/swarm\/guard\.py\)/);
  assert.match(github.pathRefusal('engineer', 'league/ops/context.py', github.ROLES, 'research'), /protected \(league\/ops\/context\.py\)/);
  assert.match(github.pathRefusal('engineer', 'league/ledger.py', github.ROLES, 'research'), /no role may write this file/);
  const admitted = github.admit({ role: 'engineer', lane: 'research', slug: 'preflight-reads', title: 'Faster preflight reads', base_sha: HEAD,
    files: [{ path: 'league/swarm/preflight.py', content: 'x = 1\n' }] });
  assert.match(admitted.branch, /^engineer\/research\/preflight-reads-[0-9a-f]{8}$/);
  assert.equal(github.engineerLane(admitted.branch), 'research');
  assert.equal(github.admit({ role: 'architect', slug: 'x1', title: 't', files: [{ path: 'league/strategies/x.py', content: '' }] }).branch.slice(0, 17), 'merton/architect/');
  const refused = github.admit({ role: 'engineer', lane: 'research', slug: 'live-tweak', title: 't', files: [{ path: 'league/live/step.py', content: '' }] });
  assert.equal(refused.status, 403);
});

test('the engineer opens engineer/ branches inside its lanes\' surfaces only, through the proposal route', () => {
  for (const path of github.ENGINEER_HELD) {
    assert.match(github.pathRefusal('engineer', path, github.ROLES, 'research'), /held from the engineer in this release/, path);
  }
  for (const [lane, path] of [['research', 'league/swarm/preflight.py'],
    ['memory', 'league/swarm/architect.py'], ['data', 'league/sailbox.py'], ['scheduler', 'league/tests/test_harness_candidate_screen.py']]) {
    assert.equal(github.pathRefusal('engineer', path, github.ROLES, lane), null, path);
  }
  for (const path of ['league/swarm/hook.py', 'league/swarm/pool.py', 'league/tests/test_swarm_researcher.py', 'docs/runs/desk/2026-10-05.md',
    'league/tests/test_harness_candidate_x/evil.py', 'league/tests/test_harness_candidate_.py', 'league/tests/test_harness_candidate_x.pyc',
    `league/tests/test_harness_candidate_${'x'.repeat(81)}.py`, 'League/Swarm/Researcher.py']) {
    for (const lane of Object.keys(github.ENGINEER_LANES)) {
      assert.match(github.pathRefusal('engineer', path, github.ROLES, lane), /outside the engineer's lane surfaces|no automated change may write this file/, `${lane} ${path}`);
    }
  }
  // league/swarm/mechanisms.py is in the memory lane's table and league/swarm/loop.py is the scheduler lane's, and
  // neither is in a harness lane's surface: its own lane may not write it.
  assert.match(github.pathRefusal('engineer', 'league/swarm/mechanisms.py', github.ROLES, 'memory'), /outside the engineer's lane surfaces/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/loop.py', github.ROLES, 'scheduler'), /outside the engineer's lane surfaces/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/bands.py', github.ROLES, 'research'), /no automated change may write this file: protected/);
  assert.match(github.pathRefusal('engineer', 'league/ops/budget.py', github.ROLES, 'research'), /protected \(league\/ops\/budget\.py\)/);
  assert.match(github.pathRefusal('engineer', 'league/ops/agenda.py', github.ROLES, 'research'), /protected \(league\/ops\/\)/);
  assert.match(github.pathRefusal('engineer', 'league/structure_core.py', github.ROLES, 'research'), /protected \(league\/structure_core\.py\)/);
  assert.match(github.pathRefusal('engineer', 'league/swarm/gate/__init__.py', github.ROLES, 'research'), /shadow/);
  assert.match(github.pathRefusal('engineer', 'league/ledger.py', github.ROLES, 'research'), /no role may write this file/);
  const admitted = github.admit({ role: 'engineer', lane: 'research', slug: 'preflight-screen', title: 'Screen unrunnable programs', base_sha: HEAD,
    files: [{ path: 'league/swarm/preflight.py', content: 'x = 1\n' }] });
  assert.match(admitted.branch, /^engineer\/research\/preflight-screen-[0-9a-f]{8}$/);
  assert.equal(github.admit({ role: 'architect', slug: 'x1', title: 't', files: [{ path: 'league/strategies/x.py', content: '' }] }).branch.slice(0, 17), 'merton/architect/');
  for (const path of ['league/live/step.py', 'league/swarm/models.py', 'league/house.py', 'league/swarm/hook.py', 'league/swarm/mechanisms.py',
    'league/swarm/loop.py']) {
    for (const lane of Object.keys(github.ENGINEER_LANES)) {
      assert.equal(github.admit({ role: 'engineer', lane, slug: 'tweak-x', title: 't', base_sha: HEAD, files: [{ path, content: '' }] }).status, 403, `${lane} ${path}`);
    }
  }
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
  assert.equal(put.body.commit_title, 'Faster preflight reads (#77)');
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
    // WP8b: the lane is part of the name, and only a known lane in the gateway's own shape is one.
    [{ head: { ...enginePull().head, ref: 'engineer/preflight-reads-1a2b3c4d' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, ref: 'engineer/execution/preflight-reads-1a2b3c4d' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, ref: 'engineer/Research/preflight-reads-1a2b3c4d' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, ref: 'engineer/research/preflight-reads' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, ref: 'engineer/research/x/preflight-reads-1a2b3c4d' } }, 403, 'branch'],
    [{ head: { ...enginePull().head, ref: 'engineer/constructor/preflight-reads-1a2b3c4d' } }, 403, 'branch'],
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
    { filename: 'league/swarm/preflight.py', previous_filename: 'league/ops/budget.py', status: 'renamed' },
    { filename: '.github/workflows/checks.yml', status: 'modified' },
    { filename: 'gateway/lib/merge.mjs', status: 'modified' },
    { filename: 'league/config.json', status: 'modified' },
    { filename: '.gitattributes', status: 'added' },
    { filename: null, status: 'added' },
    { filename: 'league/structure_core.py', status: 'modified' },
    { filename: 'league/__init__.py', status: 'modified' },
    { filename: 'ltcm/performance.py', status: 'modified' },
    { filename: 'league/swarm/policy.json', status: 'added' },
    { filename: 'league/swarm/gate/__init__.py', status: 'added' },
    { filename: 'league/constitution/__init__.py', status: 'added' },
    { filename: 'league/swarm/researcher.py', previous_filename: 'league/swarm/guard.py', status: 'renamed' },
    { filename: 'league/ops/agenda.py', status: 'modified' },                       // the House's job framework
    { filename: 'league/tests/test_harness_candidate_x.pyc', status: 'added' },     // bytecode under a test's name
  ]) {
    const hub = fakeHub();
    hub.files.set(77, [{ filename: 'league/swarm/preflight.py', status: 'modified' }, file]);
    const gate = gateAt();
    await approve(gate, hub);
    const refused = await mergeIt(gate, hub);
    assert.equal(refused.response.status, 403, JSON.stringify(file));
    assert.equal(refused.body.refused, 'protected_path');
    assert.equal(writes(hub).length, 0);
  }
});

test('every changed file, by its name and its name before a rename, is inside the branch s own lane, or nothing merges (WP8b)', async () => {
  const OTHER_LANE = ['lane_path', /outside the research lane/];
  const NO_LANE = ['outside_surface', /outside the engineer's lane surfaces/];
  for (const [file, refusal, says] of [
    [{ filename: 'league/swarm/architect.py', status: 'modified' }, ...OTHER_LANE],                 // the memory lane's
    [{ filename: 'league/sailbox.py', status: 'removed' }, ...OTHER_LANE],                          // the data lane's
    // In no lane's surface at all: refused as that, before the branch's lane is asked.
    [{ filename: 'league/swarm/loop.py', status: 'modified' }, ...NO_LANE],                         // the scheduler lane's table, no harness lane's surface
    [{ filename: 'league/swarm/pool.py', status: 'modified' }, ...NO_LANE],                         // research-class, but no lane's
    [{ filename: 'League/Swarm/Preflight.py', status: 'modified' }, ...NO_LANE],                    // the lane's file, in another case
    [{ filename: 'league/tests/test_harness_candidate_.py', status: 'added' }, ...NO_LANE],
    [{ filename: 'league/tests/test_harness_candidate_x/y.py', status: 'added' }, ...NO_LANE],
    [{ filename: 'league/tests/test_ops_agenda.py', status: 'added' }, ...NO_LANE],
    [{ filename: 'league/tests/test_harness_candidate_ok.py', previous_filename: 'league/tests/test_swarm_loop.py', status: 'renamed' }, ...NO_LANE],
    [{ filename: 'league/swarm/preflight_v2.py', previous_filename: 'league/swarm/preflight.py', status: 'renamed' }, ...NO_LANE],
  ]) {
    const hub = fakeHub();
    hub.files.set(77, [{ filename: 'league/swarm/preflight.py', status: 'modified' }, file]);
    const gate = gateAt();
    await approve(gate, hub);
    const refused = await mergeIt(gate, hub);
    assert.equal(refused.response.status, 403, JSON.stringify(file));
    assert.equal(refused.body.refused, refusal, JSON.stringify(file));
    assert.match(refused.body.error, says);
    assert.equal(writes(hub).length, 0);
    assert.equal(gate.status(NOW).autonomy.merges.count, 0);
  }
  // A protected file is refused as one, even listed after a file outside the lane.
  const hub = fakeHub();
  hub.files.set(77, [{ filename: 'league/swarm/pool.py', status: 'modified' }, { filename: 'league/ops/grant.py', status: 'modified' }]);
  const gate = gateAt();
  await approve(gate, hub);
  assert.equal((await mergeIt(gate, hub)).body.refused, 'protected_path');
  // Each lane merges its own surface and the new tests, a rename inside it included.
  for (const [lane, files] of Object.entries({
    research: ['league/swarm/preflight.py'],
    memory: ['league/swarm/architect.py', 'league/swarm/strategist.py', 'league/swarm/diagnostician.py', 'league/swarm/seeds.py'],
    data: ['league/sailbox.py', 'league/data_job.py'],
  })) {
    const lanes = fakeHub();
    const listed = [...files.map(filename => ({ filename, status: 'modified' })),
      { filename: `league/tests/test_harness_candidate_${lane}_2.py`, status: 'added' }];
    lanes.files.set(77, listed);
    lanes.pulls.set(77, enginePull({ changed_files: listed.length, head: { ...enginePull().head, ref: `engineer/${lane}/lane-change-0f0f0f0f` } }));
    const at = gateAt();
    await approve(at, lanes);
    const merged = await mergeIt(at, lanes);
    assert.equal(merged.response.status, 200, `${lane}: ${JSON.stringify(merged.body)}`);
    assert.equal(merged.body.merged, true);
    // And another lane's branch may not carry them.
    const other = fakeHub();
    other.files.set(77, listed);
    other.pulls.set(77, enginePull({ changed_files: listed.length, head: { ...enginePull().head, ref: `engineer/${lane === 'data' ? 'scheduler' : 'data'}/lane-change-0f0f0f0f` } }));
    const elsewhere = gateAt();
    await approve(elsewhere, other);
    assert.equal((await mergeIt(elsewhere, other)).body.refused, 'lane_path', lane);
  }
  // The research lane's held files (github.ENGINEER_HELD: the live path loads them) do not merge, on its own branch too.
  for (const filename of github.ENGINEER_HELD) {
    const held = fakeHub();
    held.files.set(77, [{ filename, status: 'modified' }]);
    held.pulls.set(77, enginePull({ changed_files: 1, head: { ...enginePull().head, ref: 'engineer/research/lane-change-0f0f0f0f' } }));
    const at = gateAt();
    await approve(at, held);
    const kept = await mergeIt(at, held);
    assert.equal(kept.response.status, 403, filename);
    assert.equal(kept.body.refused, 'outside_surface');
    assert.match(kept.body.error, /held from the engineer in this release/);
    assert.equal(writes(held).length, 0);
  }
  // The memory lane's table names league/swarm/mechanisms.py (league/ci.py ENGINEER_LANES); no harness lane's surface
  // does (github.ENGINEER_SURFACE), so its own lane's branch does not merge it until harness_lanes.py declares it.
  const undeclared = fakeHub();
  undeclared.files.set(77, [{ filename: 'league/swarm/architect.py', status: 'modified' }, { filename: 'league/swarm/mechanisms.py', status: 'added' }]);
  undeclared.pulls.set(77, enginePull({ head: { ...enginePull().head, ref: 'engineer/memory/lane-change-0f0f0f0f' } }));
  const behind = gateAt();
  await approve(behind, undeclared);
  const kept = await mergeIt(behind, undeclared);
  assert.equal(kept.response.status, 403);
  assert.equal(kept.body.refused, 'outside_surface');
  assert.equal(writes(undeclared).length, 0);
  // Nor does the scheduler lane's branch merge league/swarm/loop.py, all its table holds: the harness loop's scheduler
  // lane changes the Scheduler class's body alone, and the file holds the Sail guard's brake besides. Changed, removed
  // or renamed, alone or beside a new test, nothing merges; the lane's branch merges a new test and no more.
  for (const listed of [
    [{ filename: 'league/swarm/loop.py', status: 'modified' }],
    [{ filename: 'league/swarm/loop.py', status: 'modified' }, { filename: 'league/tests/test_harness_candidate_scheduler_2.py', status: 'added' }],
    [{ filename: 'league/swarm/loop.py', status: 'removed' }],
    [{ filename: 'league/tests/test_harness_candidate_scheduler_2.py', previous_filename: 'league/swarm/loop.py', status: 'renamed' }],
  ]) {
    const loop = fakeHub();
    loop.files.set(77, listed);
    loop.pulls.set(77, enginePull({ changed_files: listed.length, head: { ...enginePull().head, ref: 'engineer/scheduler/lane-change-0f0f0f0f' } }));
    const held = gateAt();
    await approve(held, loop);
    const stopped = await mergeIt(held, loop);
    assert.equal(stopped.response.status, 403, JSON.stringify(listed));
    assert.equal(stopped.body.refused, 'outside_surface', JSON.stringify(listed));
    assert.match(stopped.body.error, /league\/swarm\/loop\.py: outside the engineer's lane surfaces/);
    assert.equal(writes(loop).length, 0);
    assert.equal(held.status(NOW).autonomy.merges.count, 0);
  }
  const tests = fakeHub();
  tests.files.set(77, [{ filename: 'league/tests/test_harness_candidate_scheduler_2.py', status: 'added' }]);
  tests.pulls.set(77, enginePull({ changed_files: 1, head: { ...enginePull().head, ref: 'engineer/scheduler/lane-change-0f0f0f0f' } }));
  const open = gateAt();
  await approve(open, tests);
  assert.equal((await mergeIt(open, tests)).body.merged, true);
});

test('an engineer lane may only ADD a test: a retained candidate test modified, removed or renamed is refused (V3-A)', async () => {
  for (const file of [
    { filename: 'league/tests/test_harness_candidate_prior.py', status: 'modified' },
    { filename: 'league/tests/test_harness_candidate_prior.py', status: 'removed' },
    { filename: 'league/tests/test_harness_candidate_prior_2.py', previous_filename: 'league/tests/test_harness_candidate_prior.py', status: 'renamed' },
    { filename: 'league/tests/test_harness_candidate_prior.py', status: 'changed' },
    // GitHub names a file's earlier name only for a rename or a copy: an "added" test that carries one is not new.
    { filename: 'league/tests/test_harness_candidate_prior_3.py', previous_filename: 'league/tests/test_harness_candidate_prior.py', status: 'added' },
  ]) {
    const hub = fakeHub();
    hub.files.set(77, [{ filename: 'league/swarm/preflight.py', status: 'modified' }, file]);
    const gate = gateAt();
    await approve(gate, hub);
    const refused = await mergeIt(gate, hub);
    assert.equal(refused.response.status, 403, JSON.stringify(file));
    assert.equal(refused.body.refused, 'outside_surface', JSON.stringify(file));
    assert.match(refused.body.error, /may only add a new test/);
    assert.equal(writes(hub).length, 0);
  }
  const hub = fakeHub();
  hub.files.set(77, [{ filename: 'league/swarm/preflight.py', status: 'modified' },
    { filename: 'league/tests/test_harness_candidate_fresh.py', status: 'added' }]);
  const gate = gateAt();
  await approve(gate, hub);
  assert.equal((await mergeIt(gate, hub)).response.status, 200);
});

test('a pull request changing anything outside the engineer\'s lane surfaces, or an existing test, is never merged', async () => {
  for (const file of [
    { filename: 'league/swarm/hook.py', status: 'modified' },
    { filename: 'league/swarm/pool.py', status: 'modified' },
    { filename: 'league/tests/test_swarm_researcher.py', status: 'modified' },
    { filename: 'league/tests/test_harness_candidate_agenda.py', status: 'modified' },
    { filename: 'league/tests/test_harness_candidate_agenda.py', status: 'removed' },
    { filename: 'league/tests/test_harness_candidate_new.py', previous_filename: 'league/tests/test_harness_candidate_old.py', status: 'renamed' },
    { filename: 'league/swarm/researcher.py', previous_filename: 'league/swarm/hook.py', status: 'renamed' },
    { filename: 'README.md', status: 'modified' },
  ]) {
    const hub = fakeHub();
    hub.files.set(77, [{ filename: 'league/swarm/preflight.py', status: 'modified' }, file]);
    const gate = gateAt();
    await approve(gate, hub);
    const refused = await mergeIt(gate, hub);
    assert.equal(refused.response.status, 403, JSON.stringify(file));
    assert.equal(refused.body.refused, 'outside_surface', JSON.stringify(file));
    assert.equal(writes(hub).length, 0);
  }
});

test('the changed files are read whole, page by page, or the merge is refused', async () => {
  // 230 files over three pages, none protected and all in the lane: read whole, merged.
  const many = Array.from({ length: 230 }, (_, n) => ({ filename: `league/tests/test_harness_candidate_${n}.py`, status: 'added' }));
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
    hub.files.set(number, [{ filename: 'league/swarm/preflight.py', status: 'modified' }]);
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

test('a 5xx on the merge is no answer: the place stays taken, so a third merge cannot follow on the same day', async () => {
  const hub = fakeHub({ script: key => (key === 'PUT /pulls/77/merge' ? new Response(JSON.stringify({ message: 'Bad Gateway' }), { status: 502 }) : undefined) });
  const gate = gateAt();
  await approve(gate, hub);
  const lost = await mergeIt(gate, hub);
  assert.equal(lost.response.status, 502);
  assert.equal(lost.body.merged, 'unknown');
  assert.equal(lost.body.refused, 'no_answer');
  assert.equal(gate.status(NOW).autonomy.merges.count, 1, 'GitHub\'s edge may have answered after the merge was made');
  assert.equal(gate.status(NOW).autonomy.merges.recent[0].outcome, 'unknown');
  // Another pull request takes the second place, and a third is refused before GitHub hears of it.
  for (const [number, sha] of [[78, '1'.repeat(40)], [79, '2'.repeat(40)]]) {
    hub.pulls.set(number, enginePull({ number, head: { ...enginePull().head, sha } }));
    hub.files.set(number, [{ filename: 'league/swarm/preflight.py', status: 'modified' }]);
    hub.pulls.get(number).changed_files = 1;
    hub.runs.push(passedRun(sha, { id: 9000 + number }));
    hub.jobs.set(9000 + number, passedJobs());
    await approve(gate, hub, number, sha);
  }
  assert.equal((await mergeIt(gate, hub, 78, '1'.repeat(40))).response.status, 200);
  assert.equal((await mergeIt(gate, hub, 79, '2'.repeat(40))).body.cap, 'merge_day');
  // Each 4xx is GitHub's no, and gives the place back.
  for (const status of [403, 404, 405, 409, 422]) {
    const refusing = fakeHub({ script: key => (key === 'PUT /pulls/77/merge' ? new Response(JSON.stringify({ message: 'no' }), { status }) : undefined) });
    const fresh = gateAt();
    await approve(fresh, refusing);
    const answer = await mergeIt(fresh, refusing);
    assert.equal(answer.body.merged, false, String(status));
    assert.equal(answer.body.refused, 'github', String(status));
    assert.equal(fresh.status(NOW).autonomy.merges.count, 0, String(status));
  }
});

test('while the kill switch is engaged no merge is made; the docs and review routes still answer', async () => {
  const hub = fakeHub();
  const gate = gateAt();
  await approve(gate, hub);
  gate.setKill(true, NOW);
  const halted = await mergeIt(gate, hub);
  assert.equal(halted.response.status, 423);
  assert.equal(halted.body.cap, 'kill_switch');
  assert.equal(writes(hub).length, 0);
  assert.equal(gate.status(NOW).autonomy.merges.count, 0);
  const page = await call(ask('POST', '/v1/github/docs', { path: 'docs/runs/desk/2026-10-05.md', content: '# Desk\n' }), { gate, hub });
  assert.equal(page.response.status, 200, JSON.stringify(page.body));
  gate.setKill(false, NOW);
  assert.equal((await mergeIt(gate, hub)).response.status, 200);
});

test('a reject recorded while the merge reads GitHub stops it in the step that takes the day\'s place', async () => {
  let gate;
  const hub = fakeHub({ script: key => {
    if (key.startsWith('GET /actions/runs/9001/jobs')) gate.reviewRecord({ pr: 77, sha: HEAD, verdict: 'reject', reasons: ['Found a leak on a second read.'] });
    return undefined;
  } });
  gate = gateAt();
  await approve(gate, hub);
  const refused = await mergeIt(gate, hub);
  assert.equal(refused.response.status, 409);
  assert.equal(refused.body.refused, 'review_rejected');
  assert.equal(writes(hub).length, 0);
  assert.equal(gate.status(NOW).autonomy.merges.count, 0);
});

test('a reject outlives the verdict list; once one is forgotten, no approve it could have been about counts', async () => {
  const gate = gateAt();
  const hub = fakeHub();
  hub.pulls.set(77, enginePull({ created_at: '2026-10-01T12:00:00Z' }));
  // Approved, then rejected on a second look; then 250 approves of other commits push both out of the verdict list.
  gate.reviewRecord({ pr: 77, sha: HEAD, verdict: 'approve', reasons: ['x'], at: NOW - 3000 });
  gate.reviewRecord({ pr: 77, sha: HEAD, verdict: 'reject', reasons: ['x'], at: NOW - 2000 });
  for (let n = 0; n < 250; n += 1) gate.reviewRecord({ pr: 1000 + n, sha: n.toString(16).padStart(40, '0'), verdict: 'approve', reasons: ['x'], at: NOW - 1000 });
  assert.equal(gate.reviewFor({ pr: 77, sha: HEAD }).verdict, 'reject');
  assert.equal((await approve(gate, hub)).body.refused, 'review_rejected');
  assert.equal((await mergeIt(gate, hub)).body.refused, 'review_rejected');
  // 2,000 later rejects push it out of the rejects kept: the approve before it no longer counts, and a new approve of a
  // pull request opened before the forgotten reject is refused.
  for (let n = 0; n < 2000; n += 1) gate.reviewRecord({ pr: 5000 + n, sha: n.toString(16).padStart(40, 'f'), verdict: 'reject', reasons: ['x'], at: NOW - 500 });
  assert.deepEqual(gate.reviewFor({ pr: 77, sha: HEAD }), { verdict: null });
  const late = await approve(gate, hub);
  assert.equal(late.response.status, 409);
  assert.equal(late.body.refused, 'review_forgotten');
  assert.equal((await mergeIt(gate, hub)).body.refused, 'review_missing');
  assert.equal(writes(hub).length, 0);
  // A pull request opened after every forgotten reject is reviewed and merged as before.
  hub.pulls.set(77, enginePull({ created_at: '2026-10-05T15:59:59Z' }));
  assert.equal((await approve(gate, hub)).response.status, 200);
  assert.equal((await mergeIt(gate, hub)).response.status, 200);
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
