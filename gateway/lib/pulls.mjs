// The engineer's pull requests, read and tidied (LTCM v3, release V3-A; the review of the V3-A integration).
//
// The House holds no GitHub credential, so two things the engineer job needs go through here:
//
//  - `GET /v1/github/pr/<n>/files?head_sha=<40 hex>`: the exact change a pull request carries at one head commit, file by
//    file with GitHub's patch, read whole (a list that cannot be read whole, or a head that moved, is refused), so the
//    automated reviewer judges the diff that `POST /v1/github/merge` would merge and nothing else. Read-only and free.
//  - `POST /v1/github/close` `{ pr, head_sha }`: close one open engineer pull request at its exact head (a revision or a
//    reject supersedes it), inside the merge route's own walls on the branch (`merge.readPull`): an engineer branch of
//    this repository aimed at main. It closes; it never deletes a branch, merges, pushes or reopens.

import { client, Refusal, refused as refusal } from './github.mjs';
import { readPull, MAX_FILES } from './merge.mjs';

const PAGE = 100;
//: The most patch text one answer carries, a file and in all. A patch cut short says so (`patch_truncated`), and an
//: answer with any patch missing or cut says it is not `complete`: a reviewer must not approve what it could not read.
export const MAX_PATCH_CHARS = 600 * 1024;
export const MAX_TOTAL_PATCH_CHARS = 1536 * 1024;

const SHA = /^[0-9a-f]{40}$/;

/** `head_sha` from a files read's query, or `{ error, status }`. */
export function admitFilesQuery(url) {
  const head = url.searchParams.get('head_sha');
  if (typeof head !== 'string' || !SHA.test(head)) return { error: 'head_sha must be a full 40-hex commit id.', status: 400 };
  return { headSha: head };
}

/**
 * The files `number` changes at `headSha`: `{ number, head, base, branch, complete, files: [{ filename, status,
 * previous_filename, additions, deletions, patch, patch_truncated }] }` or `{ error, status, refused }`.
 */
export async function pullFiles({ repo, token, number, headSha, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    const found = await github.ask('pull request', 'GET', `/pulls/${number}`);
    if (found.status === 404) throw new Refusal('No such pull request.', 404, 'not_found');
    const pull = github.need(found, 'pull request');
    if (pull.head?.sha !== headSha) throw new Refusal('The pull request\'s head is not the commit named.', 409, 'head_moved');
    const expected = pull.changed_files;
    if (!Number.isSafeInteger(expected) || expected < 0) throw new Refusal('The pull request\'s changed files cannot be counted.', 409, 'files');
    if (expected > MAX_FILES) throw new Refusal(`The pull request changes ${expected} files; at most ${MAX_FILES} are read here.`, 403, 'files');
    const listed = [];
    for (let page = 1; listed.length < expected && page <= Math.ceil(MAX_FILES / PAGE); page += 1) {
      const rows = await github.get('changed files', 'GET', `/pulls/${number}/files?per_page=${PAGE}&page=${page}`);
      if (!Array.isArray(rows)) throw new Refusal('GitHub\'s list of changed files was not a list.', 502, 'files');
      listed.push(...rows);
      if (rows.length < PAGE) break;
    }
    if (listed.length !== expected) {
      throw new Refusal(`GitHub listed ${listed.length} changed files of ${expected}: the list was not read whole.`, 409, 'files');
    }
    let room = MAX_TOTAL_PATCH_CHARS;
    let complete = true;
    const files = listed.map(file => {
      const text = typeof file?.patch === 'string' ? file.patch : null;
      const keep = text === null ? null : text.slice(0, Math.max(0, Math.min(MAX_PATCH_CHARS, room)));
      const truncated = text !== null && keep.length < text.length;
      // A file with changes and no patch (GitHub leaves it out of a large or binary diff) was not read either.
      if (truncated || (text === null && Number(file?.changes) > 0)) complete = false;
      room -= keep === null ? 0 : keep.length;
      return {
        filename: String(file?.filename ?? ''), status: String(file?.status ?? ''),
        ...(file?.previous_filename !== undefined ? { previous_filename: String(file.previous_filename) } : {}),
        additions: Number(file?.additions) || 0, deletions: Number(file?.deletions) || 0,
        patch: keep, patch_truncated: truncated,
      };
    });
    return {
      number: pull.number, head: headSha, base: String(pull.base?.sha || ''), branch: String(pull.head?.ref || ''),
      complete, files,
    };
  } catch (error) {
    return refusal(error, token);
  }
}

/**
 * Close one open engineer pull request at `headSha` (the merge route's walls on the branch, `merge.readPull`).
 * `{ closed: true }` or `{ error, status, refused }`.
 */
export async function closePull({ repo, token, number, headSha, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    await readPull(github, { repo, number, headSha });
    const done = await github.get('close', 'PATCH', `/pulls/${number}`, { state: 'closed' });
    if (done.state !== 'closed') throw new Refusal('GitHub did not close the pull request.', 502, 'github');
    return { closed: true };
  } catch (error) {
    return refusal(error, token);
  }
}
