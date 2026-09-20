// Pull requests: which paths each role may write, what a proposal's branch is called, the exact
// calls GitHub receives, what a retry does, and what the VM is told about CI.

import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';

import * as github from '../lib/github.mjs';
import { createGate } from '../lib/gate.mjs';
import { fakeGitHub, memoryStore, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';

const STRATEGY = { path: 'league/strategies/kalshi_weather_favorites.py', content: 'EDGE = 0.04\n' };
const proposal = (extra = {}) => ({
  role: 'architect', slug: 'kalshi-weather-favorites', title: 'Add the Kalshi weather favorites strategy',
  body: 'Favorites above 90 cents settled yes 97% of the time in the replay.', files: [STRATEGY], ...extra,
});
const open = (hub, extra) => github.openPullRequest({ repo: GITHUB_REPO, token: GITHUB_TOKEN, proposal: github.admit(proposal(extra)), fetcher: hub.fetcher });
const reply = (status, data) => new Response(JSON.stringify(data), { status });

test('each role writes under its own paths and nowhere else', () => {
  const allowed = {
    architect: ['league/strategies/kalshi_weather_favorites.py', 'league/strategies/pairs/spread.py'],
    toolsmith: ['league/tools/orderbook_depth.py', 'league/tests/test_tool_orderbook_depth.py'],
    operator: ['league/config.json'],
    designer: ['league/game.json'],
    teacher: ['league/playbook/2026-09-19-favorites.md'],
  };
  assert.deepEqual(Object.keys(github.ROLES), Object.keys(allowed));
  for (const [role, paths] of Object.entries(allowed)) {
    for (const path of paths) {
      assert.equal(github.pathRefusal(role, path), null, `${role} may write ${path}`);
      // What one role may write, every other role may not.
      for (const other of Object.keys(allowed).filter(name => name !== role)) {
        assert.match(github.pathRefusal(other, path), /outside what the/, `${other} may not write ${path}`);
      }
    }
  }
  for (const [role, path] of [
    ['architect', 'league/strategies.py'], ['architect', 'league/config.json'], ['architect', 'ltcm/service.py'],
    ['toolsmith', 'league/tests/test_ledger.py'], ['toolsmith', 'league/tests/conftest.py'],
    // `exactly` means exactly: not a sibling, not a longer name, not a directory of that name.
    ['operator', 'league/config.json.bak'], ['operator', 'league/config.jsonx'], ['operator', 'league/config.json/x'], ['operator', 'league/game.json'],
    ['designer', 'league/config.json'], ['designer', 'league/game.jsonc'],
    ['teacher', 'league/playbook.md'], ['teacher', 'README.md'],
    ['janitor', 'league/strategies/x.py'], ['constructor', 'league/strategies/x.py'],
  ]) {
    assert.notEqual(github.pathRefusal(role, path), null, `${role} may not write ${path}`);
  }
});

test('a path is a normalized repository path: no way up, no way out, nothing of git s', () => {
  for (const path of [
    '../league/strategies/x.py', 'league/strategies/../ci.py', 'league/strategies/../../.github/workflows/ci.yml',
    'league/strategies/./x.py', 'league/strategies//x.py', 'league/strategies/', '/league/strategies/x.py',
    'league\\strategies\\x.py', 'league/strategies/..\\ci.py', 'league/strategies/x.py\n', 'league/strategies/\x00x.py',
    'league/strategies/.git/config', 'league/strategies/.GIT/hooks/pre-commit', 'league/strategies/.gitattributes', 'league/strategies/.gitmodules',
    `league/strategies/${'x'.repeat(200)}.py`, '', null, 42, ['league/strategies/x.py'],
  ]) {
    assert.notEqual(github.pathRefusal('architect', path), null, JSON.stringify(path));
  }
  assert.equal(github.pathRefusal('architect', `league/strategies/${'x'.repeat(179)}.py`), null, '200 characters is the ceiling, not over it');
});

test('the judges are refused for every role, even under rules loosened to allow everything', () => {
  const judges = [
    ...github.FORBIDDEN_FILES, 'gateway/worker.mjs', 'gateway/lib/github.mjs', 'gateway/wrangler.jsonc',
    '.github/workflows/ci.yml', '.github/CODEOWNERS', 'League/CI.py', 'league/Constitution.py', 'GATEWAY/worker.mjs', '.GitHub/workflows/merge.yml',
  ];
  assert.deepEqual(github.FORBIDDEN_FILES, [
    ...['constitution', 'ci', 'ledger', 'book', 'evaluator', 'stats', 'auditor', 'watchdog', 'safety', 'replay', 'updater'].map(name => `league/${name}.py`),
    'league/campaigns.json', 'league/campaigns.py', 'league/funded.py', 'league/experiments.py', 'league/recordings.py', 'league/research_jobs.py', 'league/capabilities.py', 'league/parameters.py',
  ]);
  for (const role of Object.keys(github.ROLES)) {
    const loosened = { [role]: { under: [''] } };
    assert.equal(github.pathRefusal(role, 'anything/at/all.py', loosened), null, 'the loosened rules do allow everything else');
    for (const path of judges) {
      assert.notEqual(github.pathRefusal(role, path), null, `${role} ${path}`);
      assert.match(github.pathRefusal(role, path, loosened), /no role may write this file|git's own files/, `${role} ${path}, loosened`);
    }
  }
});

test('a proposal is checked whole before GitHub hears of it', () => {
  const ok = github.admit(proposal());
  assert.equal(ok.error, undefined);
  assert.equal(ok.role, 'architect');
  assert.deepEqual(ok.files, [STRATEGY]);

  // A refused path is a 403 that names it; the first bad file refuses the whole proposal.
  const refused = github.admit(proposal({ files: [STRATEGY, { path: 'league/ci.py', content: 'PASS = True\n' }] }));
  assert.equal(refused.status, 403);
  assert.equal(refused.path, 'league/ci.py');
  assert.match(refused.error, /"league\/ci\.py" is refused: no role may write this file/);
  const wandering = github.admit(proposal({ role: 'teacher' }));
  assert.equal(wandering.status, 403);
  assert.match(wandering.error, /kalshi_weather_favorites\.py" is refused: outside what the teacher may write/);

  const file = n => ({ path: `league/strategies/s${n}.py`, content: `N = ${n}\n` });
  const twelve = Array.from({ length: 12 }, (_, n) => file(n));
  assert.equal(github.admit(proposal({ files: twelve })).error, undefined, 'twelve files is the ceiling');
  const exactly = 'x'.repeat(64 * 1024);
  assert.equal(github.admit(proposal({ files: [{ ...STRATEGY, content: exactly }] })).error, undefined, '64 KiB is the ceiling');
  assert.equal(github.admit(proposal({ files: [{ ...STRATEGY, content: '' }] })).error, undefined, 'an empty file is a file');
  assert.equal(github.admit(proposal({ body: undefined })).body, '', 'a body is optional');

  for (const [why, bad] of [
    ['no files', { files: [] }], ['thirteen files', { files: [...twelve, file(12)] }], ['files not a list', { files: { 0: STRATEGY } }],
    ['one byte too many', { files: [{ ...STRATEGY, content: exactly + 'x' }] }],
    ['bytes, not characters', { files: [{ ...STRATEGY, content: '\u00e9'.repeat(40 * 1024) }] }],
    ['content not text', { files: [{ ...STRATEGY, content: { py: 'x' } }] }], ['content missing', { files: [{ path: STRATEGY.path }] }],
    ['content not unicode', { files: [{ ...STRATEGY, content: 'x = "\ud800"' }] }],
    ['the same path twice', { files: [STRATEGY, { ...STRATEGY, content: 'EDGE = 0.4\n' }] }], ['a file that is not one', { files: ['league/strategies/x.py'] }],
    ['unknown role', { role: 'janitor' }], ['inherited role', { role: 'toString' }], ['role not text', { role: ['architect'] }],
    ['slug too short', { slug: 'a' }], ['slug too long', { slug: 'a'.repeat(50) }], ['slug with a slash', { slug: 'a/../b' }], ['slug upper case', { slug: 'Weather' }], ['slug leading dash', { slug: '-weather' }],
    ['title missing', { title: undefined }], ['title blank', { title: '   ' }], ['title too long', { title: 'x'.repeat(121) }], ['title two lines', { title: 'one\ntwo' }],
    ['body too long', { body: 'x'.repeat(8001) }], ['body not text', { body: 7 }],
  ]) {
    assert.equal(github.admit(proposal(bad)).status, 400, why);
  }
  for (const bad of [null, [], 'text', 7]) assert.equal(github.admit(bad).status, 400);
  assert.equal(github.admit(proposal({ slug: 'a'.repeat(49), title: 'x'.repeat(120), body: 'x'.repeat(8000) })).error, undefined, 'the ceilings themselves pass');
});

test('the branch is named from the role, the slug and the files, and the same proposal is the same branch', () => {
  const other = { path: 'league/strategies/alpha.py', content: 'A = 1\n' };
  const branch = github.branchName('architect', 'kalshi-weather-favorites', [STRATEGY, other]);
  assert.match(branch, /^merton\/architect\/kalshi-weather-favorites-[0-9a-f]{8}$/);
  // The hash is sha256 over the files in path order, as [path, content] pairs.
  const canonical = JSON.stringify([[other.path, other.content], [STRATEGY.path, STRATEGY.content]]);
  assert.equal(branch.slice(-8), createHash('sha256').update(canonical).digest('hex').slice(0, 8));

  assert.equal(github.branchName('architect', 'kalshi-weather-favorites', [other, STRATEGY]), branch, 'file order does not matter');
  assert.equal(github.branchName('architect', 'kalshi-weather-favorites', [{ ...other, note: 'ignored' }, STRATEGY]), branch, 'only path and content count');
  assert.equal(github.admit(proposal({ files: [other, STRATEGY], title: 'Another title', body: 'Other words.' })).branch, branch, 'nor do the title or the body');
  assert.notEqual(github.branchName('architect', 'kalshi-weather-favorites', [{ ...STRATEGY, content: 'EDGE = 0.05\n' }, other]), branch, 'a changed file is a new branch');
  assert.notEqual(github.branchName('architect', 'kalshi-weather-favorites', [STRATEGY]), branch);
  // A path and a content cannot be shuffled into each other s place.
  assert.notEqual(github.branchName('teacher', 'x1', [{ path: 'ab', content: 'c' }]).slice(-8), github.branchName('teacher', 'x1', [{ path: 'a', content: 'bc' }]).slice(-8));
});

test('GitHub receives blobs, a tree on main, a commit, the branch and the pull request, in that order', async () => {
  const hub = fakeGitHub();
  const main = hub.refs.get('main');
  const tool = [{ path: 'league/tools/depth.py', content: 'def depth(): return 1\n' }, { path: 'league/tests/test_tool_depth.py', content: 'def test_depth(): assert True\n' }];
  const result = await open(hub, { role: 'toolsmith', slug: 'depth-tool', files: tool });
  const branch = github.branchName('toolsmith', 'depth-tool', tool);

  assert.deepEqual(hub.calls.map(call => call.key), [
    'GET /git/ref/heads/main', `GET /git/commits/${main}`,
    'POST /git/blobs', 'POST /git/blobs', 'POST /git/trees', 'POST /git/commits', 'POST /git/refs', 'POST /pulls',
  ]);
  for (const call of hub.calls) {
    assert.ok(call.url.startsWith(`https://api.github.com/repos/${GITHUB_REPO}/`), call.url);
    assert.equal(call.headers.Authorization, `Bearer ${GITHUB_TOKEN}`);
    assert.equal(call.headers.Accept, 'application/vnd.github+json');
    assert.equal(call.headers['X-GitHub-Api-Version'], '2022-11-28');
    assert.equal(call.headers['User-Agent'], 'ltcm-gateway');
    assert.equal(call.headers['Content-Type'], call.method === 'POST' ? 'application/json' : undefined);
    assert.equal(call.redirect, 'manual', 'a redirect would carry the token to another host');
  }
  const [, , blobA, blobB, tree, commit, ref, pull] = hub.calls.map(call => call.body);
  // Files go up in path order, whatever order they arrived in.
  assert.deepEqual(blobA, { content: tool[1].content, encoding: 'utf-8' });
  assert.deepEqual(blobB, { content: tool[0].content, encoding: 'utf-8' });
  assert.equal(tree.base_tree.length, 40, 'the tree is built on the head commit s tree');
  assert.deepEqual(tree.tree.map(entry => [entry.path, entry.mode, entry.type]), [
    ['league/tests/test_tool_depth.py', '100644', 'blob'], ['league/tools/depth.py', '100644', 'blob'],
  ]);
  assert.deepEqual(commit.parents, [main]);
  assert.equal(commit.message, 'Add the Kalshi weather favorites strategy\n\nOpened by Merton (toolsmith) through the LTCM gateway.');
  assert.deepEqual(ref, { ref: `refs/heads/${branch}`, sha: result.head });
  assert.deepEqual(pull, {
    title: 'Add the Kalshi weather favorites strategy', head: branch, base: 'main',
    body: 'Favorites above 90 cents settled yes 97% of the time in the replay.\n\n---\n\nOpened by Merton (toolsmith) through the LTCM gateway.',
  });
  assert.deepEqual(result, { ok: true, branch, number: 41, url: `https://github.com/${GITHUB_REPO}/pull/41`, head: hub.refs.get(branch), created: true });
  assert.equal(github.pullBody('teacher', ''), '---\n\nOpened by Merton (teacher) through the LTCM gateway.', 'a proposal with no words still says who opened it');
});

test('a retry of the same proposal reuses its branch and returns its pull request', async () => {
  const hub = fakeGitHub();
  const first = await open(hub);
  const before = hub.calls.length;
  const again = await open(hub);
  assert.deepEqual({ ...again, created: true }, first, 'the same branch, number, url and head commit');
  assert.equal(again.created, false, 'and nothing new was made, so the day s cap is not charged');
  assert.deepEqual(hub.calls.slice(before).map(call => call.key.replace(/[0-9a-f]{40}/, '<sha>').replace(/\?.*/, '?')), [
    'GET /git/ref/heads/main', 'GET /git/commits/<sha>', 'POST /git/blobs', 'POST /git/trees', 'POST /git/commits',
    'POST /git/refs', `GET /git/ref/heads/${first.branch}`, 'GET /git/commits/<sha>', 'POST /pulls', 'GET /pulls?',
  ]);
  const find = hub.calls.at(-1);
  assert.equal(find.url, `https://api.github.com/repos/${GITHUB_REPO}/pulls?head=${encodeURIComponent(`bwoods1998:${first.branch}`)}&base=main&state=open&per_page=1`);
  assert.equal(hub.pulls.length, 1);

  // The branch exists but its pull request never opened (the first attempt died between the two).
  const half = fakeGitHub({ script: key => (key === 'POST /pulls' && half.pulls.length === 0 && !half.healed ? reply(500, { message: 'Server Error' }) : undefined) });
  const died = await open(half);
  assert.equal(died.status, 502);
  assert.equal(died.created, true, 'the branch was made, so the attempt is counted');
  half.healed = true;
  const healed = await open(half);
  assert.equal(healed.ok, true);
  assert.equal(healed.created, false);
  assert.equal(healed.head, half.refs.get(healed.branch), 'the pull request is for the commit the branch already had');
});

test('a retry after main has moved still finds its branch, and a branch holding something else is refused', async () => {
  const hub = fakeGitHub();
  const first = await open(hub);
  hub.moveMain();
  const again = await open(hub);
  assert.equal(again.ok, true, again.error);
  assert.equal(again.number, first.number);
  assert.equal(again.head, first.head);
  assert.equal(again.created, false);
  assert.ok(hub.calls.some(call => /^GET \/git\/trees\/[0-9a-f]{40}\?recursive=1$/.test(call.key)), 'the branch s own files were compared');

  // Someone else s branch under the same name: never adopted, never overwritten.
  const squatted = fakeGitHub();
  squatted.refs.set(first.branch, squatted.refs.get('main'));
  const refused = await open(squatted);
  assert.equal(refused.status, 409);
  assert.match(refused.error, /already exists and holds something else/);
  assert.equal(refused.created, false);
  assert.equal(squatted.refs.get(first.branch), squatted.refs.get('main'), 'the ref was not moved');
  assert.equal(squatted.pulls.length, 0);
  assert.ok(!squatted.calls.some(call => call.method === 'PATCH' || call.method === 'DELETE' || call.method === 'PUT'));
});

test('a proposal that changes nothing is refused before a branch exists', async () => {
  const hub = fakeGitHub();
  await open(hub);
  // The pull request merged: main now holds the file, and the workflow deleted the branch.
  hub.refs.set('main', hub.refs.get(github.admit(proposal()).branch));
  hub.refs.delete(github.admit(proposal()).branch);
  const before = hub.calls.length;
  const same = await open(hub);
  assert.equal(same.status, 409);
  assert.match(same.error, /changes nothing on main/);
  assert.equal(same.created, false);
  assert.deepEqual(hub.calls.slice(before).filter(call => call.method === 'POST').map(call => call.key), ['POST /git/blobs', 'POST /git/trees']);
});

test('any GitHub failure is a 502 with a short reason, and the token is in none of them', async () => {
  const steps = ['GET /git/ref/heads/main', 'GET /git/commits/', 'POST /git/blobs', 'POST /git/trees', 'POST /git/commits', 'POST /git/refs', 'POST /pulls'];
  for (const step of steps) {
    // A GitHub that answers badly and echoes the credential back, as a careless proxy might.
    const loud = fakeGitHub({ script: key => (key.startsWith(step) ? reply(step === 'POST /pulls' ? 422 : 403, { message: `Bad credentials for Bearer ${GITHUB_TOKEN}\n  at line 1`, errors: [{ message: `token ${GITHUB_TOKEN}` }] }) : undefined) });
    const failed = await open(loud);
    assert.equal(failed.status, 502, step);
    assert.match(failed.error, /^GitHub answered HTTP 4\d\d \(.+\): Bad credentials/, step);
    assert.ok(failed.error.length <= 200 && !failed.error.includes('\n'), step);
    assert.equal(JSON.stringify(failed).includes(GITHUB_TOKEN), false, step);
    assert.equal(failed.created, step === 'POST /pulls', `${step}: only a failure after the branch exists is counted`);

    // A GitHub that does not answer at all. Silence on the branch call may hide a branch.
    const silent = fakeGitHub({ script: key => { if (key.startsWith(step)) throw new Error(`connect failed with ${GITHUB_TOKEN}`); } });
    const lost = await open(silent);
    assert.equal(lost.status, 502, step);
    assert.match(lost.error, /^GitHub did not answer \(.+\)\.$/, step);
    assert.equal(JSON.stringify(lost).includes(GITHUB_TOKEN), false, step);
    assert.equal(lost.created, step === 'POST /git/refs' || step === 'POST /pulls', step);
  }

  // Answers that are not what they should be are failures too, not crashes.
  for (const [step, body] of [['GET /git/ref/heads/main', { object: {} }], ['POST /git/blobs', { sha: 'not-a-sha' }], ['POST /pulls', { html_url: 'x' }]]) {
    const odd = await open(fakeGitHub({ script: key => (key === step ? reply(200, body) : undefined) }));
    assert.equal(odd.status, 502, step);
    assert.match(odd.error, /carried no (sha|pull request number)/, step);
  }
  const html = await open(fakeGitHub({ script: key => (key === 'POST /git/trees' ? new Response('<html>bad gateway</html>', { status: 200 }) : undefined) }));
  assert.equal(html.status, 502);
});

test('check runs are counted, and nothing unfinished or unseen is a success', () => {
  const run = (status, conclusion = null) => ({ status, conclusion });
  const sum = (runs, total = runs.length) => github.summarizeChecks({ total_count: total, check_runs: runs });
  assert.deepEqual(sum([]), { total: 0, completed: 0, failed: 0, conclusion: 'pending' }, 'CI has not started: not a pass');
  assert.deepEqual(sum([run('queued'), run('in_progress')]), { total: 2, completed: 0, failed: 0, conclusion: 'pending' });
  assert.deepEqual(sum([run('completed', 'success'), run('in_progress')]), { total: 2, completed: 1, failed: 0, conclusion: 'pending' });
  assert.deepEqual(sum([run('completed', 'success'), run('completed', 'neutral'), run('completed', 'skipped')]), { total: 3, completed: 3, failed: 0, conclusion: 'success' });
  for (const bad of ['failure', 'cancelled', 'timed_out', 'action_required', 'stale', 'startup_failure', null]) {
    assert.deepEqual(sum([run('completed', 'success'), run('completed', bad)]), { total: 2, completed: 2, failed: 1, conclusion: 'failure' }, String(bad));
  }
  assert.equal(sum([run('completed', 'failure'), run('in_progress')]).conclusion, 'failure', 'one failure is enough; the rest need not finish');
  assert.equal(sum([run('completed', 'success')], 140).conclusion, 'pending', 'runs beyond the page read are not assumed to have passed');
  for (const junk of [null, undefined, {}, { check_runs: 'x' }, { check_runs: [null] }]) assert.equal(github.summarizeChecks(junk).conclusion, 'pending');
});

test('the status of a pull request is read with the gateway s credential and carries none of it', async () => {
  const hub = fakeGitHub({ checks: { total_count: 2, check_runs: [{ status: 'completed', conclusion: 'success' }, { status: 'completed', conclusion: 'failure' }] } });
  const opened = await open(hub);
  const before = hub.calls.length;
  const status = await github.pullStatus({ repo: GITHUB_REPO, token: GITHUB_TOKEN, number: opened.number, fetcher: hub.fetcher });
  assert.deepEqual(status, {
    number: 41, state: 'open', merged: false, mergeable_state: 'clean', head: opened.head,
    checks: { total: 2, completed: 2, failed: 1, conclusion: 'failure' },
  });
  assert.deepEqual(hub.calls.slice(before).map(call => call.key), ['GET /pulls/41', `GET /commits/${opened.head}/check-runs?per_page=100`]);
  assert.equal(hub.calls.at(-1).headers.Authorization, `Bearer ${GITHUB_TOKEN}`);

  const missing = await github.pullStatus({ repo: GITHUB_REPO, token: GITHUB_TOKEN, number: 999, fetcher: hub.fetcher });
  assert.deepEqual(missing, { error: 'No such pull request.', status: 404 });
  const broken = await github.pullStatus({ repo: GITHUB_REPO, token: GITHUB_TOKEN, number: 41, fetcher: async () => reply(401, { message: `Bad credentials ${GITHUB_TOKEN}` }) });
  assert.equal(broken.status, 502);
  assert.equal(JSON.stringify(broken).includes(GITHUB_TOKEN), false);
});

test('the gateway is configured only by a token and a repository name that is one', () => {
  assert.deepEqual(github.configured({ GITHUB_TOKEN, GITHUB_REPO }), { repo: GITHUB_REPO, token: GITHUB_TOKEN });
  for (const env of [{}, { GITHUB_TOKEN }, { GITHUB_REPO }, { GITHUB_TOKEN: '  ', GITHUB_REPO },
    { GITHUB_TOKEN, GITHUB_REPO: 'long-term-capital-management' }, { GITHUB_TOKEN, GITHUB_REPO: 'a/b/../../user' }, { GITHUB_TOKEN, GITHUB_REPO: 'a/b?x=1' }]) {
    assert.equal(github.configured(env), null, JSON.stringify(Object.keys(env)));
  }
});

test('the day s pull requests are counted on a UTC day, reserved in one step and given back by name', () => {
  const late = Date.parse('2026-09-15T23:30:00Z');  // 19:30 in New York: the same trading day, the same UTC day
  const gate = createGate({ store: memoryStore(), env: { CAP_TIMEZONE: 'America/New_York' }, now: () => late });
  assert.equal(github.dayCap({}), 12);
  assert.equal(github.dayCap({ GITHUB_MAX_PULLS_PER_DAY: '3' }), 3);
  assert.equal(github.dayCap({ GITHUB_MAX_PULLS_PER_DAY: '0' }), 0, 'zero switches proposals off');
  for (const junk of ['', 'many', '-1', '2.5']) assert.equal(github.dayCap({ GITHUB_MAX_PULLS_PER_DAY: junk }), 12, junk);

  for (let n = 1; n <= 12; n += 1) assert.deepEqual(gate.pullReserve({ at: late }), { ok: true, day: '2026-09-15', count: n });
  const refused = gate.pullReserve({ at: late });
  assert.equal(refused.status, 429);
  assert.equal(refused.cap, 'github_day');
  assert.match(refused.error, /cap of 12 pull requests/);
  assert.deepEqual(gate.status(late).github, { day: '2026-09-15', pull_requests: 12, cap: 12 });

  assert.deepEqual(gate.pullRefund({ day: '2026-09-15', at: late }), { ok: true });
  assert.equal(gate.pullsToday(late), 11);
  assert.equal(gate.pullReserve({ at: late }).ok, true);

  // Half an hour later it is a new UTC day though the floor s trading day has hours to run.
  const next = late + 45 * 60000;
  assert.equal(gate.pullsToday(next), 0);
  assert.deepEqual(gate.pullRefund({ day: '2026-09-15', at: next }), { ok: false }, 'yesterday s place is not given back to today');
  assert.deepEqual(gate.pullReserve({ at: next }), { ok: true, day: '2026-09-16', count: 1 });
  assert.equal(gate.status(next).today.day, '2026-09-15', 'the order counters still roll on the floor s own day');
});
