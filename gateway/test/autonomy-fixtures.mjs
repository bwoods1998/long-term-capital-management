// A GitHub small enough to read for the V3-A routes (WP8): the engineer's pull requests (their files, the checks.yml
// runs and jobs on a commit, the squash merge) and the Contents API the desk's docs commits use. State is plain data a
// test edits: `pulls`, `files`, `runs`, `jobs`, `contents`. `script(key, init, body)` may answer a call first (`key`
// is `METHOD /path` inside the repository). Every call is kept in `calls`, its headers included.

import { createHash } from 'node:crypto';
import { GITHUB_REPO } from './helpers.mjs';

export const HEAD = 'a'.repeat(40);
export const OTHER = 'b'.repeat(40);

const reply = (status, data) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const gitBlob = text => createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${Buffer.byteLength(text)}\u0000`), Buffer.from(text)])).digest('hex');

/** An open engineer pull request of the research lane at HEAD, as GitHub's `GET /pulls/<n>` answers it. */
export const enginePull = (extra = {}) => ({
  number: 77, state: 'open', merged: false, draft: false, title: 'Faster preflight reads', changed_files: 2,
  head: { ref: 'engineer/research/preflight-reads-1a2b3c4d', sha: HEAD, repo: { full_name: GITHUB_REPO } },
  base: { ref: 'main', repo: { full_name: GITHUB_REPO } },
  ...extra,
});

/** A checks.yml run on `sha` that passed, and its three required jobs, passed. */
export const passedRun = (sha = HEAD, extra = {}) => ({
  id: 9001, head_sha: sha, status: 'completed', conclusion: 'success', created_at: '2026-10-05T14:00:00Z',
  repository: { full_name: GITHUB_REPO }, head_repository: { full_name: GITHUB_REPO }, ...extra,
});
export const passedJobs = () => ['gateway', 'tests (3.11)', 'tests (3.14)'].map((name, i) => ({ id: 100 + i, name, status: 'completed', conclusion: 'success' }));

export function fakeHub({ script = () => undefined } = {}) {
  const calls = [];
  const state = {
    calls,
    pulls: new Map([[77, enginePull()]]),
    files: new Map([[77, [{ filename: 'league/swarm/preflight.py', status: 'modified' },
      { filename: 'league/tests/test_harness_candidate_preflight.py', status: 'added' }]]]),
    runs: [passedRun()],
    jobs: new Map([[9001, passedJobs()]]),
    contents: new Map(),       // path -> text on main
    commits: [],               // the docs commits made, in order
    merged: [],                // the merges made
  };
  state.fetcher = async (url, init = {}) => {
    const prefix = `https://api.github.com/repos/${GITHUB_REPO}`;
    const path = String(url).startsWith(prefix) ? String(url).slice(prefix.length) : String(url);
    const key = `${init.method} ${path}`;
    const body = init.body === undefined ? undefined : JSON.parse(init.body);
    calls.push({ url: String(url), key, method: init.method, headers: init.headers, body, redirect: init.redirect });
    const scripted = await script(key, init, body);
    if (scripted) return scripted;
    let match;
    if ((match = /^GET \/pulls\/(\d+)$/.exec(key))) {
      const pull = state.pulls.get(Number(match[1]));
      return pull ? reply(200, pull) : reply(404, { message: 'Not Found' });
    }
    if ((match = /^GET \/pulls\/(\d+)\/files\?per_page=(\d+)&page=(\d+)$/.exec(key))) {
      const all = state.files.get(Number(match[1])) || [];
      const per = Number(match[2]);
      const page = Number(match[3]);
      return reply(200, all.slice((page - 1) * per, page * per));
    }
    if ((match = /^GET \/actions\/workflows\/checks\.yml\/runs\?head_sha=([0-9a-f]{40})&per_page=50$/.exec(key))) {
      return reply(200, { total_count: state.runs.length, workflow_runs: state.runs.filter(run => run.head_sha === match[1]) });
    }
    if ((match = /^GET \/actions\/runs\/(\d+)\/jobs\?filter=latest&per_page=100$/.exec(key))) {
      const jobs = state.jobs.get(Number(match[1])) || [];
      return reply(200, { total_count: jobs.length, jobs });
    }
    if ((match = /^PUT \/pulls\/(\d+)\/merge$/.exec(key))) {
      const pull = state.pulls.get(Number(match[1]));
      if (!pull || pull.state !== 'open') return reply(405, { message: 'Pull Request is not mergeable' });
      if (body.sha !== pull.head.sha) return reply(409, { message: 'Head branch was modified. Review and try the merge again.' });
      Object.assign(pull, { state: 'closed', merged: true });
      const sha = createHash('sha1').update(`merge ${pull.number} ${body.sha}`).digest('hex');
      state.merged.push({ number: pull.number, ...body, merge_sha: sha });
      return reply(200, { sha, merged: true, message: 'Pull Request successfully merged' });
    }
    if ((match = /^GET \/contents\/(docs\/runs\/desk\/[^?]+)\?ref=main$/.exec(key))) {
      const text = state.contents.get(match[1]);
      return text === undefined ? reply(404, { message: 'Not Found' }) : reply(200, { type: 'file', path: match[1], sha: gitBlob(text) });
    }
    if ((match = /^PUT \/contents\/(docs\/runs\/desk\/.+)$/.exec(key))) {
      const held = state.contents.get(match[1]);
      if (held !== undefined && body.sha !== gitBlob(held)) return reply(409, { message: `${match[1]} does not match ${body.sha}` });
      if (held === undefined && body.sha) return reply(422, { message: 'sha wasn\'t supplied.' });
      const text = Buffer.from(body.content, 'base64').toString('utf8');
      state.contents.set(match[1], text);
      const commit = createHash('sha1').update(`commit ${state.commits.length} ${text}`).digest('hex');
      state.commits.push({ path: match[1], message: body.message, branch: body.branch, commit });
      return reply(held === undefined ? 201 : 200, { content: { path: match[1], sha: gitBlob(text) }, commit: { sha: commit } });
    }
    return reply(404, { message: `unscripted: ${key}` });
  };
  return state;
}
