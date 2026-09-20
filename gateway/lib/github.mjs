// Pull requests, and nothing else (Sept 19, 2026).
//
// The frontier model proposes changes to the floor: a new strategy, a tool, a game dial, a
// lesson. The rule is that a change reaches the repository only as a pull request, and the
// credential that can open one lives here for the same reason the venue keys do: the trading VM
// can ask, it cannot push. CI on GitHub judges every pull request and a repository workflow
// merges the ones that pass. Nothing in this module merges, approves, closes or deletes.
//
// Every rule below is enforced a second time by the repository's own CI. They are enforced here
// first because this is the last place a confused or compromised VM can be stopped before its
// words become a branch: each role may write only under its own paths, and the files that judge
// the floor (the constitution, CI, the ledger, the evaluator, this gateway) are refused for every
// role, by name, even if a role's paths were loosened later.

import { createHash } from 'node:crypto';

export const HOST = 'https://api.github.com';
//: The branch every proposal is cut from and aimed at.
export const BASE = 'main';
export const MAX_FILES = 12;
export const MAX_PATH_CHARS = 200;
export const MAX_CONTENT_BYTES = 64 * 1024;
export const MAX_TITLE_CHARS = 120;
export const MAX_BODY_CHARS = 8000;
export const MAX_REQUEST_BYTES = 256 * 1024;
//: Pull requests a UTC day. A runaway loop is stopped here, not by GitHub's rate limit.
export const MAX_PULLS_PER_DAY = 12;

/** What each role may write: `under` is a path prefix, `only` is a whole path. */
export const ROLES = {
  architect: { under: ['league/strategies/'] },
  toolsmith: { under: ['league/tools/', 'league/tests/test_tool_'] },
  operator: { only: ['league/config.json'] },
  designer: { only: ['league/game.json'] },
  teacher: { under: ['league/playbook/'] },
};

//: The judges. No role writes these, whatever `ROLES` says: a proposal must never be able to
//: change the rules it is judged by, or the gateway that holds the keys.
export const FORBIDDEN_FILES = [
  'league/constitution.py', 'league/ci.py', 'league/ledger.py', 'league/book.py',
  'league/evaluator.py', 'league/stats.py', 'league/auditor.py', 'league/watchdog.py',
  'league/safety.py', 'league/replay.py', 'league/updater.py',
  'league/campaigns.json', 'league/campaigns.py', 'league/funded.py', 'league/experiments.py', 'league/recordings.py', 'league/research_jobs.py', 'league/capabilities.py',
];
export const FORBIDDEN_TREES = ['gateway/', '.github/'];

const SLUG = /^[a-z0-9][a-z0-9-]{1,48}$/;
const REPO = /^[A-Za-z0-9_.-]{1,100}\/[A-Za-z0-9_.-]{1,100}$/;

export const footer = role => `Opened by Merton (${role}) through the LTCM gateway.`;

/** `{ repo, token }` when both are set and the repository name is one, else `null`. */
export function configured(env = {}) {
  const repo = String(env.GITHUB_REPO || '').trim();
  const token = String(env.GITHUB_TOKEN || '').trim();
  return REPO.test(repo) && token ? { repo, token } : null;
}

/** Pull requests a UTC day: `GITHUB_MAX_PULLS_PER_DAY`, which only the owner's deploy can change. */
export function dayCap(env = {}) {
  const asked = String(env.GITHUB_MAX_PULLS_PER_DAY ?? '').trim();
  return /^[0-9]{1,4}$/.test(asked) ? Number(asked) : MAX_PULLS_PER_DAY;
}

/**
 * Why this role may not write this path, or `null` when it may. The shape of the path is checked
 * first, then the judges, then the role's own paths -- so a judge is refused by name even under
 * a rule table (`roles`) that would otherwise let it through.
 */
export function pathRefusal(role, path, roles = ROLES) {
  if (typeof path !== 'string' || !path) return 'a path must be a non-empty string';
  if (path.length > MAX_PATH_CHARS) return `a path is at most ${MAX_PATH_CHARS} characters`;
  // A repository path, not a filesystem one: forward slashes, no way up, nothing invisible.
  if (path.startsWith('/') || path.includes('\\') || /[\x00-\x1f\x7f]/.test(path)) return 'a path must be relative, with forward slashes';
  const segments = path.split('/');
  if (segments.some(segment => segment === '' || segment === '.' || segment === '..')) return 'a path must be normalized';
  // Compared without case, so a checkout on a case-blind disk cannot be fooled either.
  const lower = path.toLowerCase();
  if (FORBIDDEN_FILES.includes(lower) || FORBIDDEN_TREES.some(tree => lower.startsWith(tree))) return 'no role may write this file';
  // Not the directory, and not `.gitattributes` or `.gitmodules` either: they change a checkout.
  if (segments.some(segment => /^\.git/i.test(segment))) return 'a path may not name git\'s own files';
  const rule = Object.hasOwn(roles, role) ? roles[role] : null;
  if (!rule) return 'the role is unknown';
  const allowed = (rule.only || []).includes(path) || (rule.under || []).some(prefix => path.startsWith(prefix));
  return allowed ? null : `outside what the ${role} may write`;
}

/** The proposal's files in one fixed order and form, so the same proposal hashes the same. */
export function canonicalFiles(files) {
  return files
    .map(file => ({ path: file.path, content: file.content }))
    .sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
}

/** `merton/<role>/<slug>-<8 hex>`: a retry of the same proposal is the same branch. */
export function branchName(role, slug, files) {
  const canonical = JSON.stringify(canonicalFiles(files).map(file => [file.path, file.content]));
  return `merton/${role}/${slug}-${createHash('sha256').update(canonical, 'utf8').digest('hex').slice(0, 8)}`;
}

/**
 * Check a proposal before anything is sent. `{ role, slug, title, body, files, branch }` or
 * `{ error, status }`; a path refusal is a `403` that names the path.
 */
export function admit(proposal) {
  const bad = (error, status = 400, extra = {}) => ({ error, status, ...extra });
  if (!proposal || typeof proposal !== 'object' || Array.isArray(proposal)) return bad('The proposal must be a JSON object.');
  const { role, slug, title, body = '', files } = proposal;
  if (typeof role !== 'string' || !Object.hasOwn(ROLES, role)) return bad(`The role must be one of: ${Object.keys(ROLES).join(', ')}.`);
  if (typeof slug !== 'string' || !SLUG.test(slug)) return bad('The slug must be 2 to 49 of a-z, 0-9 and "-", and start with a letter or a digit.');
  if (typeof title !== 'string' || !title.trim() || title.length > MAX_TITLE_CHARS || /[\r\n]/.test(title)) {
    return bad(`The title must be one line of at most ${MAX_TITLE_CHARS} characters.`);
  }
  if (typeof body !== 'string' || body.length > MAX_BODY_CHARS) return bad(`The body must be text of at most ${MAX_BODY_CHARS} characters.`);
  if (!Array.isArray(files) || files.length < 1 || files.length > MAX_FILES) return bad(`A proposal carries 1 to ${MAX_FILES} files.`);
  const seen = new Set();
  for (const file of files) {
    if (!file || typeof file !== 'object' || Array.isArray(file)) return bad('Each file must be an object with a path and a content.');
    const refusal = pathRefusal(role, file.path);
    if (refusal) {
      const shown = String(file.path ?? '').slice(0, MAX_PATH_CHARS);
      return bad(`The path "${shown}" is refused: ${refusal}.`, 403, { path: shown });
    }
    if (seen.has(file.path)) return bad(`The path "${file.path}" appears twice.`);
    seen.add(file.path);
    // Text only: a string that is not well-formed Unicode has no UTF-8 form to commit.
    if (typeof file.content !== 'string' || !file.content.isWellFormed()) return bad(`The content of "${file.path}" must be UTF-8 text.`);
    if (Buffer.byteLength(file.content, 'utf8') > MAX_CONTENT_BYTES) return bad(`The content of "${file.path}" is over ${MAX_CONTENT_BYTES} bytes.`);
  }
  const canonical = canonicalFiles(files);
  return { role, slug, title: title.trim(), body, files: canonical, branch: branchName(role, slug, canonical) };
}

/** The pull request's text: the proposal's own words, then who opened it and how. */
export const pullBody = (role, body) => [String(body || '').trimEnd(), '---', footer(role)].filter(Boolean).join('\n\n');

/** The headers every GitHub call carries. The token goes out in this one place and never comes back. */
export const headers = (token, { write = false } = {}) => ({
  Accept: 'application/vnd.github+json',
  Authorization: `Bearer ${token}`,
  'X-GitHub-Api-Version': '2022-11-28',
  'User-Agent': 'ltcm-gateway',
  ...(write ? { 'Content-Type': 'application/json' } : {}),
});

// A reason the caller may read: one short line, and never the token, even if GitHub echoed it.
const tidy = (text, token) =>
  String(text ?? '').split(token).join('[redacted]').replace(/\s+/g, ' ').trim().slice(0, 200);

/** Why a call sequence stopped. `status` is what the gateway's caller is told. */
class Refusal extends Error {
  constructor(reason, status = 502) {
    super(reason);
    this.status = status;
  }
}

// Anything that is not a Refusal is a bug here, and a bug is reported without its details.
const refused = (error, token) => (error instanceof Refusal
  ? { error: tidy(error.message, token), status: error.status }
  : { error: 'The GitHub call failed unexpectedly.', status: 502 });

/**
 * REST calls inside one repository. `ask` returns `{ status, ok, data }` and throws only when
 * nothing answered; `need` turns an answer that is not a success into a refusal that says which
 * step failed and what GitHub said about it; `get` is both.
 */
function client({ repo, token, fetcher }) {
  const ask = async (step, method, path, body) => {
    let upstream;
    try {
      upstream = await fetcher(`${HOST}/repos/${repo}${path}`, {
        method,
        headers: headers(token, { write: body !== undefined }),
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        redirect: 'manual',
        signal: AbortSignal.timeout(20000),
      });
    } catch {
      throw new Refusal(`GitHub did not answer (${step}).`);
    }
    return { status: upstream.status, ok: upstream.ok, data: await upstream.json().catch(() => null) };
  };
  const need = (reply, step) => {
    if (reply.ok && reply.data && typeof reply.data === 'object') return reply.data;
    const said = [reply.data?.message, reply.data?.errors?.[0]?.message].filter(text => typeof text === 'string').join(' ');
    throw new Refusal(`GitHub answered HTTP ${reply.status} (${step})${said ? `: ${said}` : '.'}`);
  };
  return { ask, need, get: async (step, method, path, body) => need(await ask(step, method, path, body), step) };
}

const sha = (value, step) => {
  if (typeof value !== 'string' || !/^[0-9a-f]{40,64}$/.test(value)) throw new Refusal(`GitHub's answer carried no sha (${step}).`);
  return value;
};

/**
 * Open the pull request for an admitted proposal: blobs, a tree on top of `main`, a commit, the
 * branch, the pull request. `{ ok, branch, number, url, head, created }` or `{ error, status,
 * created }`.
 *
 * `created` is whether this attempt may have made a new branch, which is what the day's cap
 * counts. A retry finds its branch already there and its pull request already open, makes
 * nothing, and returns what the first attempt made. A branch request that never answered is
 * counted as made: no answer is not proof of no branch.
 */
export async function openPullRequest({ repo, token, proposal, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  const { role, title, files, branch } = proposal;
  let created = false;
  try {
    const parent = sha((await github.get('base ref', 'GET', `/git/ref/heads/${BASE}`)).object?.sha, 'base ref');
    const baseTree = sha((await github.get('base commit', 'GET', `/git/commits/${parent}`)).tree?.sha, 'base commit');

    const entries = [];
    for (const file of files) {
      const blob = await github.get('blob', 'POST', '/git/blobs', { content: file.content, encoding: 'utf-8' });
      entries.push({ path: file.path, mode: '100644', type: 'blob', sha: sha(blob.sha, 'blob') });
    }
    const tree = sha((await github.get('tree', 'POST', '/git/trees', { base_tree: baseTree, tree: entries })).sha, 'tree');
    // Git is content-addressed: the same tree back means every file already reads this way.
    if (tree === baseTree) throw new Refusal(`The proposal changes nothing on ${BASE}.`, 409);

    const message = `${title}\n\n${footer(role)}`;
    let head = sha((await github.get('commit', 'POST', '/git/commits', { message, tree, parents: [parent] })).sha, 'commit');

    created = true;  // from here a silence may hide a branch
    const ref = await github.ask('branch', 'POST', '/git/refs', { ref: `refs/heads/${branch}`, sha: head });
    if (!ref.ok) {
      created = false;  // GitHub answered, and the answer was not a new branch
      // 422 is "Reference already exists": the retry's case. Anything else is GitHub's no.
      if (ref.status !== 422) github.need(ref, 'branch');
      head = await existingBranch(github, { branch, tree, entries });
    }

    const pull = await github.ask('pull request', 'POST', '/pulls', { title, head: branch, base: BASE, body: pullBody(role, proposal.body) });
    let opened = pull.data;
    if (pull.status === 422) {
      // An open pull request for this head is the retry's answer; any other 422 is GitHub's no.
      const query = `?head=${encodeURIComponent(`${repo.split('/')[0]}:${branch}`)}&base=${BASE}&state=open&per_page=1`;
      opened = (await github.get('find pull request', 'GET', `/pulls${query}`))[0];
      if (!opened) github.need(pull, 'pull request');
    } else {
      github.need(pull, 'pull request');
    }
    if (!Number.isInteger(opened?.number)) throw new Refusal('GitHub\'s answer carried no pull request number.');
    return { ok: true, branch, number: opened.number, url: String(opened.html_url || ''), head, created };
  } catch (error) {
    return { ...refused(error, token), created };
  }
}

/**
 * The commit an existing branch points at, when the branch already holds this proposal. The same
 * tree is the plain case. When `main` has moved since the first attempt the trees differ though
 * the proposal does not, so the branch's own files are compared, blob for blob.
 */
async function existingBranch(github, { branch, tree, entries }) {
  const head = sha((await github.get('existing branch', 'GET', `/git/ref/heads/${branch}`)).object?.sha, 'existing branch');
  const theirs = sha((await github.get('existing commit', 'GET', `/git/commits/${head}`)).tree?.sha, 'existing commit');
  if (theirs === tree) return head;
  const listing = await github.get('existing tree', 'GET', `/git/trees/${theirs}?recursive=1`);
  const held = new Map((Array.isArray(listing.tree) ? listing.tree : []).map(entry => [entry?.path, entry?.sha]));
  if (entries.every(entry => held.get(entry.path) === entry.sha)) return head;
  throw new Refusal(`The branch ${branch} already exists and holds something else.`, 409);
}

/**
 * Check runs, counted. Anything unfinished is `pending`, and so is no run at all: a pull request
 * CI has not looked at yet has not passed. A finished run passes only if GitHub says it
 * succeeded, was neutral or was skipped.
 */
export function summarizeChecks(data) {
  const runs = Array.isArray(data?.check_runs) ? data.check_runs : [];
  const total = Math.max(Number(data?.total_count) || 0, runs.length);
  const done = runs.filter(run => run?.status === 'completed');
  const failed = done.filter(run => !['success', 'neutral', 'skipped'].includes(run?.conclusion)).length;
  const conclusion = failed > 0 ? 'failure' : total === 0 || done.length < total ? 'pending' : 'success';
  return { total, completed: done.length, failed, conclusion };
}

/** A pull request and its CI, so the VM can watch a proposal without any GitHub credential. */
export async function pullStatus({ repo, token, number, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    const found = await github.ask('pull request', 'GET', `/pulls/${number}`);
    if (found.status === 404) throw new Refusal('No such pull request.', 404);
    const pull = github.need(found, 'pull request');
    const head = sha(pull.head?.sha, 'pull request');
    const checks = await github.get('check runs', 'GET', `/commits/${head}/check-runs?per_page=100`);
    return {
      number: pull.number, state: String(pull.state || ''), merged: pull.merged === true,
      mergeable_state: String(pull.mergeable_state || 'unknown'), head, checks: summarizeChecks(checks),
    };
  } catch (error) {
    return refused(error, token);
  }
}
