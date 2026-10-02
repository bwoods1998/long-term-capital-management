// The engineer's merges (LTCM v3, release V3-A, WP8; the owner's decision D5).
//
// The engineer's research-class pull requests merge on green CI plus an automated adversarial review, with no human
// step. This module holds the walls of that merge; the gateway is the only place a merge can be made from, because the
// GitHub token lives here and nowhere on the House. `POST /v1/github/review` records a reviewer's verdict for one exact
// head commit (the Gate keeps it); `POST /v1/github/merge` squash-merges a pull request only when ALL of these hold:
//
//  - its branch is `engineer/<lane>/<slug>-<8 hex>` with a known lane (github.ENGINEER_LANES), lives in this repository
//    (never a fork) and is aimed at `main`; it is open and no draft;
//  - its head is the commit the caller names, and GitHub is told to merge exactly that commit (a head that moved
//    between the checks and the merge is GitHub's 409, and nothing merges);
//  - the `checks.yml` workflow's latest run on that commit finished `success`, with its jobs `gateway`, `tests (3.11)`
//    and `tests (3.14)` each `success`;
//  - an `approve` verdict is recorded for that exact commit and no `reject` is (a rejected commit stays rejected: a
//    revision is a new commit, reviewed again);
//  - no file it changes, adds, removes or renames (either name) is protected (lib/protected.mjs), and every one is inside
//    its branch's lane: that lane's surface or a new `league/tests/test_harness_candidate_*.py` (WP8b; the same list
//    the proposal route admits, `github.laneRefusal`), read from GitHub's own list of the pull request's files, whole (a
//    list that cannot be read whole refuses the merge);
//  - fewer than MERGES_PER_DAY merges were made today, New York's day.
//
// Every refusal names its rule in `refused`. Nothing here approves on GitHub, pushes, re-runs CI or closes anything.

import { client, Refusal, refused as refusal, sha as needSha, ENGINEER_PREFIX, ENGINEER_TEST, BASE, engineerLane, laneRefusal } from './github.mjs';
import { protectedRefusal } from './protected.mjs';

//: The workflow whose run on the exact head commit must have succeeded, and the jobs it must have run and passed.
export const WORKFLOW = 'checks.yml';
export const REQUIRED_JOBS = Object.freeze(['gateway', 'tests (3.11)', 'tests (3.14)']);
//: Merges a New York day. A constant: only the owner's deploy changes it.
export const MERGES_PER_DAY = 2;
//: The calendar the merge and docs days roll on.
export const DAY_ZONE = 'America/New_York';
//: The most changed files a merged pull request may carry: three pages of GitHub's list. More is refused unread.
export const MAX_FILES = 300;
const PAGE = 100;
export const VERDICTS = Object.freeze(['approve', 'reject']);
export const MAX_REASONS = 20;
export const MAX_REASON_CHARS = 1000;
export const MAX_REQUEST_BYTES = 64 * 1024;

const SHA = /^[0-9a-f]{40}$/;
const PR = n => Number.isSafeInteger(n) && n > 0 && n < 1e9;

/** `{ pr, head_sha }` for a merge request, or `{ error, status }`. */
export function admitMerge(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { error: 'The request must be a JSON object.', status: 400 };
  if (!PR(body.pr)) return { error: 'pr must be a pull request number.', status: 400 };
  if (typeof body.head_sha !== 'string' || !SHA.test(body.head_sha)) return { error: 'head_sha must be a full 40-hex commit id.', status: 400 };
  return { pr: body.pr, head_sha: body.head_sha };
}

/**
 * `{ pr, head_sha, verdict, reasons }` for a review, or `{ error, status }`. `reasons` is one string or a list of them,
 * never empty: a verdict always says why.
 */
export function admitReview(body) {
  const merge = admitMerge(body);
  if (merge.error) return merge;
  if (!VERDICTS.includes(body.verdict)) return { error: `verdict must be one of: ${VERDICTS.join(', ')}.`, status: 400 };
  const list = typeof body.reasons === 'string' ? [body.reasons] : body.reasons;
  if (!Array.isArray(list) || list.length < 1 || list.length > MAX_REASONS) {
    return { error: `reasons must be 1 to ${MAX_REASONS} lines of text.`, status: 400 };
  }
  const reasons = [];
  for (const reason of list) {
    if (typeof reason !== 'string' || !reason.trim() || !reason.isWellFormed() || reason.length > MAX_REASON_CHARS) {
      return { error: `each reason is non-empty text of at most ${MAX_REASON_CHARS} characters.`, status: 400 };
    }
    reasons.push(reason.trim());
  }
  return { ...merge, verdict: body.verdict, reasons };
}

/**
 * Why this pull request (GitHub's `GET /pulls/<n>` answer) is not one the engineer's walls admit at `headSha`, or null.
 * `{ error, status, refused }`.
 */
export function pullRefusal(pull, { repo, headSha }) {
  const no = (error, refused, status = 409) => ({ error, status, refused });
  if (!pull || typeof pull !== 'object') return no('GitHub\'s answer carried no pull request.', 'github', 502);
  if (pull.state !== 'open' || pull.merged === true) return no('The pull request is not open.', 'not_open');
  if (pull.draft === true) return no('The pull request is a draft.', 'draft');
  if (engineerLane(pull.head?.ref) === null) return no(`Only an ${ENGINEER_PREFIX}<lane>/<slug>-<hash> branch merges here.`, 'branch', 403);
  if (pull.head?.repo?.full_name !== repo) return no('The branch is not in this repository.', 'fork', 403);
  if (pull.base?.ref !== BASE || pull.base?.repo?.full_name !== repo) return no(`The pull request is not aimed at ${BASE}.`, 'base', 403);
  if (pull.head?.sha !== headSha) return no('The pull request\'s head is not the commit named.', 'head_moved');
  return null;
}

/** The pull request, read from GitHub, checked against `pullRefusal`. Throws a Refusal. */
async function readPull(github, { repo, number, headSha }) {
  const found = await github.ask('pull request', 'GET', `/pulls/${number}`);
  if (found.status === 404) throw new Refusal('No such pull request.', 404, 'not_found');
  const pull = github.need(found, 'pull request');
  const why = pullRefusal(pull, { repo, headSha });
  if (why) throw new Refusal(why.error, why.status, why.refused);
  return pull;
}

/**
 * Every file the pull request changes, read whole from GitHub's list (`GET /pulls/<n>/files`, a page of 100 at a time),
 * and refused when any of them, by its name or its name before a rename, is protected (`protected_path`) or outside
 * the lane its branch names (`lane_path`). A list longer than MAX_FILES, or one whose length is not the pull request's
 * own `changed_files`, refuses the merge: it was not read whole.
 */
async function vetFiles(github, pull, number) {
  const expected = pull.changed_files;
  if (!Number.isSafeInteger(expected) || expected < 1) throw new Refusal('The pull request\'s changed files cannot be counted.', 409, 'files');
  if (expected > MAX_FILES) throw new Refusal(`The pull request changes ${expected} files; at most ${MAX_FILES} merge here.`, 403, 'files');
  const files = [];
  for (let page = 1; files.length < expected && page <= Math.ceil(MAX_FILES / PAGE); page += 1) {
    const listed = await github.get('changed files', 'GET', `/pulls/${number}/files?per_page=${PAGE}&page=${page}`);
    if (!Array.isArray(listed)) throw new Refusal('GitHub\'s list of changed files was not a list.', 502, 'files');
    files.push(...listed);
    if (listed.length < PAGE) break;
  }
  if (files.length !== expected) {
    throw new Refusal(`GitHub listed ${files.length} changed files of ${expected}: the list was not read whole.`, 409, 'files');
  }
  const names = files.flatMap(file => [file?.filename, ...(file?.previous_filename !== undefined ? [file.previous_filename] : [])]);
  // Every protected name first, so a protected file is always refused as one, wherever it sits in the list.
  for (const name of names) {
    const why = protectedRefusal(name);
    if (why) throw new Refusal(`The pull request changes ${String(name).slice(0, 200)}: ${why}.`, 403, 'protected_path');
  }
  const lane = engineerLane(pull.head?.ref);
  for (const name of names) {
    const why = laneRefusal(lane, name);
    if (why) throw new Refusal(`The pull request changes ${String(name).slice(0, 200)}: ${why}.`, 403, 'lane_path');
  }
  // A lane may only ADD a test (harness_lanes' NEW_TEST): an earlier candidate's retained test is never modified,
  // removed or renamed away by a later engineer pull request.
  if (lane) {
    for (const file of files) {
      const touched = [file?.filename, file?.previous_filename].some(name => typeof name === 'string' && ENGINEER_TEST.test(name));
      if (touched && file?.status !== 'added') {
        throw new Refusal(`The pull request changes ${String(file?.filename).slice(0, 200)}: an engineer lane may only add a `
          + `new test, never ${String(file?.status).slice(0, 20)} one.`, 403, 'lane_path');
      }
    }
  }
  return names;
}

/**
 * The `checks.yml` run that judges `headSha`: the latest run of that workflow on exactly that commit, in this
 * repository, finished `success`, with every REQUIRED_JOBS job finished `success` in its latest attempt. Throws a
 * Refusal naming `ci_missing`, `ci_pending`, `ci_failed` or `ci_jobs`.
 */
async function vetChecks(github, { repo, headSha }) {
  const listed = await github.get('checks runs', 'GET', `/actions/workflows/${WORKFLOW}/runs?head_sha=${headSha}&per_page=50`);
  const runs = (Array.isArray(listed?.workflow_runs) ? listed.workflow_runs : [])
    .filter(run => run?.head_sha === headSha && Number.isSafeInteger(run?.id) && run?.repository?.full_name === repo
      && run?.head_repository?.full_name === repo);
  if (!runs.length) throw new Refusal(`No ${WORKFLOW} run on ${headSha.slice(0, 12)}.`, 409, 'ci_missing');
  // The latest run decides: a re-run that failed after one that passed is a failure.
  const run = runs.reduce((latest, row) => (Date.parse(row.created_at || '') > Date.parse(latest.created_at || '')
    || (row.created_at === latest.created_at && row.id > latest.id) ? row : latest));
  if (run.status !== 'completed') throw new Refusal(`The ${WORKFLOW} run on ${headSha.slice(0, 12)} has not finished.`, 409, 'ci_pending');
  if (run.conclusion !== 'success') throw new Refusal(`The ${WORKFLOW} run on ${headSha.slice(0, 12)} ended ${String(run.conclusion)}.`, 409, 'ci_failed');
  const jobs = await github.get('checks jobs', 'GET', `/actions/runs/${run.id}/jobs?filter=latest&per_page=100`);
  const rows = Array.isArray(jobs?.jobs) ? jobs.jobs : [];
  for (const name of REQUIRED_JOBS) {
    const named = rows.filter(job => job?.name === name);
    if (named.length !== 1 || named[0].status !== 'completed' || named[0].conclusion !== 'success') {
      throw new Refusal(`The ${WORKFLOW} run on ${headSha.slice(0, 12)} has no passed job "${name}".`, 409, 'ci_jobs');
    }
  }
  return { run_id: run.id, jobs: [...REQUIRED_JOBS] };
}

/**
 * Read a pull request for a review: open, an engineer branch of this repository aimed at main, headed by `headSha`.
 * `{ ok, pull }` or `{ error, status, refused }`.
 */
export async function reviewTarget({ repo, token, number, headSha, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    return { ok: true, pull: await readPull(github, { repo, number, headSha }) };
  } catch (error) {
    return refusal(error, token);
  }
}

/**
 * Every check of the merge that reads GitHub, in order: the pull request, its files, its CI. `{ ok, title, files, ci }`
 * or `{ error, status, refused }`. The review and the day's count are the Gate's, checked by the router first.
 */
export async function vetMerge({ repo, token, number, headSha, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    const pull = await readPull(github, { repo, number, headSha });
    const files = await vetFiles(github, pull, number);
    const ci = await vetChecks(github, { repo, headSha });
    return { ok: true, title: String(pull.title || '').slice(0, 200), branch: pull.head.ref, files, ci };
  } catch (error) {
    return refusal(error, token);
  }
}

/** The squash commit's message: the reviewer's verdict and CI's run, so `main`'s history says how it got there. */
export const mergeMessage = ({ headSha, ci }) =>
  `Merged by the House through the LTCM gateway: ${WORKFLOW} run ${ci.run_id} passed ${REQUIRED_JOBS.join(', ')} ` +
  `on ${headSha} and the automated review approved that commit.`;

/**
 * Squash-merge `number` at exactly `headSha` (GitHub refuses with 409 when the head moved). `{ merged: true, sha }`,
 * `{ merged: false, error, status, refused }` when GitHub answered no, or `{ merged: null, error, status }` when nothing
 * answered: the merge may have been made, so the day's place stays taken.
 */
export async function squashMerge({ repo, token, number, headSha, title, ci, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  let reply;
  try {
    reply = await github.ask('merge', 'PUT', `/pulls/${number}/merge`, {
      sha: headSha, merge_method: 'squash', commit_title: `${title} (#${number})`.slice(0, 250), commit_message: mergeMessage({ headSha, ci }),
    });
  } catch (error) {
    return { merged: null, ...refusal(error, token) };
  }
  if (reply.ok && reply.data?.merged === true) {
    try {
      return { merged: true, sha: needSha(reply.data.sha, 'merge') };
    } catch {
      return { merged: true, sha: null };
    }
  }
  // GitHub answered, and the answer was not a merge: 405 (not mergeable) and 409 (the head moved) are the caller's to
  // look at again; anything else is GitHub's.
  let error;
  try {
    github.need({ ...reply, ok: false }, 'merge');
  } catch (caught) {
    error = refusal(caught, token).error;
  }
  return { merged: false, error, status: reply.status === 405 || reply.status === 409 ? 409 : 502, refused: 'github' };
}
