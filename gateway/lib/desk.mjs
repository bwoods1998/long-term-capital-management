// The desk's own docs commits (LTCM v3, release V3-A, WP8): `POST /v1/github/docs`.
//
// The House writes its public record itself: the daily scoreboard (league/ops, WP2) and the run record's daily pages.
// It holds no GitHub credential, so it asks here, and this route commits ONE file straight to `main` through GitHub's
// Contents API, within walls that do not move without the owner's deploy:
//
//  - the path is `docs/runs/desk/<YYYY-MM-DD>[-<slug>].md` and nothing else (DOCS_PATH, a real calendar date);
//  - the content is UTF-8 text (no NUL), at most DOCS_MAX_BYTES, and carries no credential this gateway holds and no
//    key-shaped text (the repository is public);
//  - the commit message is `desk: <one line>`;
//  - at most DOCS_PER_DAY commits a New York day; a post whose content already stands on `main` commits nothing and
//    takes no place.
//
// What the text says is the House's responsibility (its public filter, `league/ops` scoreboard); this route is the
// wall that keeps the commit to one file in one directory.
//
// R3's BIRTHS (Oct 19, 2026; goal-2026-10-19/R3-SPEC.md, league/events/births.py) take the same route with the same
// walls and one more directory: `docs/births/<YYYY-MM-DD>.jsonl` (BIRTHS_PATH, a real date) and nothing else there,
// and only APPENDS: the post names `lines`, 1 to BIRTHS_MAX_LINES lines of one JSON object each (no control character,
// at most BIRTH_LINE_MAX_BYTES each), which are added after what main holds (a file of whole lines, or none) and never
// replace it; the file stays under BIRTHS_FILE_MAX_BYTES; no credential, no key-shaped text; the message
// `births: <one line>`; one of the day's DOCS_PER_DAY places. The commit receipt is the birth's registration time, so
// the answer carries GitHub's own commit time (`committed_at`). Lines that all stand on main already commit nothing:
// the answer says `unchanged` with the file's latest commit and its time (a retry after an answer that never came
// learns its registration, at a time no earlier than the true one); some standing and some not is refused.

import { createHash } from 'node:crypto';
import { client, refused as refusal, sha as needSha, definiteNo, BASE } from './github.mjs';

export const DOCS_PATH = /^docs\/runs\/desk\/(\d{4})-(\d{2})-(\d{2})(-[a-z0-9-]+)?\.md$/;
export const DOCS_MAX_BYTES = 64 * 1024;
//: Commits a New York day. A constant: only the owner's deploy changes it.
export const DOCS_PER_DAY = 6;
export const DOCS_PREFIX = 'desk:';
export const MAX_MESSAGE_CHARS = 100;
//: The request: the file (escaped in JSON it can grow) and its message.
export const MAX_REQUEST_BYTES = 192 * 1024;
export const FOOTER = 'Committed by the House through the LTCM gateway (POST /v1/github/docs).';
//: R3's births: the one path pattern, appends of JSON lines only (lib/desk.mjs's header).
export const BIRTHS_PATH = /^docs\/births\/(\d{4})-(\d{2})-(\d{2})\.jsonl$/;
export const BIRTHS_MAX_LINES = 12;
export const BIRTH_LINE_MAX_BYTES = 8 * 1024;
export const BIRTHS_FILE_MAX_BYTES = 256 * 1024;
export const BIRTHS_PREFIX = 'births:';

//: The Worker secrets whose values must never reach a public commit. A value shorter than 12 characters is not looked
//: for (it would match ordinary words); every real one is longer.
export const SECRET_NAMES = Object.freeze([
  'GATEWAY_TOKEN', 'GATEWAY_ADMIN_TOKEN', 'GITHUB_TOKEN', 'ALPACA_KEY_ID', 'ALPACA_SECRET_KEY', 'ALPACA_PAPER_KEY_ID',
  'ALPACA_PAPER_SECRET_KEY', 'OPENAI_SECRET_KEY', 'CLAUDE_API_KEY', 'SAIL_API_KEY', 'KALSHI_KEY_ID', 'KALSHI_PRIVATE_KEY',
  'TYPE_SAFE_TOKEN',
]);
//: Text shaped like a credential, whoever's: a private key block, a GitHub token, an Anthropic or OpenAI key.
const KEY_SHAPES = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /\b(?:github_pat|gh[pousr])_[A-Za-z0-9_]{20,}/,
  /\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}/,
];

const realDate = (y, m, d) => {
  const at = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  return at.getUTCFullYear() === Number(y) && at.getUTCMonth() === Number(m) - 1 && at.getUTCDate() === Number(d);
};

/** True when `text` carries a secret this gateway holds or text shaped like any credential. */
export function carriesSecret(text, env = {}) {
  for (const name of SECRET_NAMES) {
    const value = typeof env[name] === 'string' ? env[name].trim() : '';
    if (value.length >= 12 && text.includes(value)) return true;
  }
  return KEY_SHAPES.some(shape => shape.test(text));
}

/**
 * `{ path, content, message }` for one docs commit, or `{ error, status, refused }`. `message` is the whole commit
 * message: `desk: <the caller's line, or the file's name>`, then the footer.
 */
export function admitDoc(body, env = {}) {
  const no = (error, refused, status = 400) => ({ error, status, refused });
  if (!body || typeof body !== 'object' || Array.isArray(body)) return no('The request must be a JSON object.', 'shape');
  const { path, content } = body;
  const match = typeof path === 'string' ? DOCS_PATH.exec(path) : null;
  if (!match || !realDate(match[1], match[2], match[3])) {
    return no('The path must be docs/runs/desk/<YYYY-MM-DD>[-<slug>].md with a real date.', 'path', 403);
  }
  if (typeof content !== 'string' || !content.length || !content.isWellFormed() || content.includes('\u0000')) {
    return no('The content must be non-empty UTF-8 text.', 'content');
  }
  if (Buffer.byteLength(content, 'utf8') > DOCS_MAX_BYTES) return no(`The content is over ${DOCS_MAX_BYTES} bytes.`, 'size', 413);
  let line = body.message === undefined ? `${path.split('/').pop()}` : body.message;
  if (typeof line !== 'string' || !line.isWellFormed() || /[\x00-\x1f\x7f]/.test(line)) return no('The message must be one line of text.', 'message');
  line = line.trim().replace(/^desk:\s*/i, '').trim();
  if (!line || line.length > MAX_MESSAGE_CHARS) return no(`The message must be 1 to ${MAX_MESSAGE_CHARS} characters.`, 'message');
  if (carriesSecret(content, env) || carriesSecret(line, env)) {
    return no('The commit would carry a credential or key-shaped text; the repository is public.', 'secret', 403);
  }
  return { path, content, message: `${DOCS_PREFIX} ${line}\n\n${FOOTER}` };
}

/** Whether a post names a births file (R3): then `admitBirths` judges it, never `admitDoc`. */
export const isBirthsPath = path => typeof path === 'string' && path.startsWith('docs/births/');

/**
 * `{ path, lines, message }` for one births append (R3), or `{ error, status, refused }`: the path
 * `docs/births/<YYYY-MM-DD>.jsonl` with a real date, `lines` of one JSON object each and no whole `content`, no
 * credential or key-shaped text, the message `births: <the caller's line, or how many>`, then the footer.
 */
export function admitBirths(body, env = {}) {
  const no = (error, refused, status = 400) => ({ error, status, refused });
  if (!body || typeof body !== 'object' || Array.isArray(body)) return no('The request must be a JSON object.', 'shape');
  const { path, lines } = body;
  const match = typeof path === 'string' ? BIRTHS_PATH.exec(path) : null;
  if (!match || !realDate(match[1], match[2], match[3])) {
    return no('The path must be docs/births/<YYYY-MM-DD>.jsonl with a real date.', 'path', 403);
  }
  if (body.content !== undefined) return no('A births file takes appended lines (`lines`), never a whole content.', 'append', 403);
  if (!Array.isArray(lines) || !lines.length || lines.length > BIRTHS_MAX_LINES) {
    return no(`lines must hold 1 to ${BIRTHS_MAX_LINES} JSON lines.`, 'lines');
  }
  for (const line of lines) {
    if (typeof line !== 'string' || !line.length || !line.isWellFormed() || /[\x00-\x1f\x7f\u2028\u2029]/.test(line)) {
      return no('Each line is one line of UTF-8 text.', 'lines');
    }
    if (Buffer.byteLength(line, 'utf8') > BIRTH_LINE_MAX_BYTES) return no(`A line is over ${BIRTH_LINE_MAX_BYTES} bytes.`, 'size', 413);
    let parsed;
    try {
      parsed = JSON.parse(line);
    } catch {
      return no('Each line must be one JSON object.', 'json');
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return no('Each line must be one JSON object.', 'json');
  }
  if (new Set(lines).size !== lines.length) return no('A line repeats.', 'lines');
  let note = body.message === undefined ? `${lines.length} birth(s)` : body.message;
  if (typeof note !== 'string' || !note.isWellFormed() || /[\x00-\x1f\x7f]/.test(note)) return no('The message must be one line of text.', 'message');
  note = note.trim().replace(/^births:\s*/i, '').trim();
  if (!note || note.length > MAX_MESSAGE_CHARS) return no(`The message must be 1 to ${MAX_MESSAGE_CHARS} characters.`, 'message');
  if (carriesSecret(lines.join('\n'), env) || carriesSecret(note, env)) {
    return no('The commit would carry a credential or key-shaped text; the repository is public.', 'secret', 403);
  }
  return { path, lines: [...lines], message: `${BIRTHS_PREFIX} ${note}\n\n${FOOTER}` };
}

/**
 * What `main` holds at a births path now: `{ ok, sha, content }` (`sha` null and `content` '' when there is no file)
 * or `{ error, status, refused }`. A directory, a symlink or a file GitHub will not return whole is refused.
 */
export async function readBirths({ repo, token, path, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    const found = await github.ask('read births', 'GET', `/contents/${path}?ref=${BASE}`);
    if (found.status === 404) return { ok: true, sha: null, content: '' };
    const data = github.need(found, 'read births');
    if (Array.isArray(data) || data.type !== 'file') return { error: 'The path holds something other than a file.', status: 409, refused: 'path' };
    if (data.encoding !== 'base64' || typeof data.content !== 'string') {
      return { error: 'GitHub did not return the births file whole.', status: 413, refused: 'size' };
    }
    const content = Buffer.from(data.content.replace(/\s+/g, ''), 'base64').toString('utf8');
    const blob = needSha(data.sha, 'read births');
    if (blobSha(content) !== blob) return { error: 'The births file read back does not match its blob.', status: 502, refused: 'github' };
    return { ok: true, sha: blob, content };
  } catch (error) {
    return refusal(error, token);
  }
}

/**
 * The append itself (no network): `{ content }` (main's text then the admitted lines, each ending its line),
 * `{ unchanged: true }` when every line stands on main already, or `{ error, status, refused }` (a file that is not
 * whole lines, some lines standing and some not, or a file grown past BIRTHS_FILE_MAX_BYTES).
 */
export function appendBirths(held, doc) {
  const old = typeof held?.content === 'string' ? held.content : '';
  if (old && !old.endsWith('\n')) return { error: 'The births file on main does not end with a whole line.', status: 409, refused: 'shape' };
  const standing = new Set(old.split('\n').filter(Boolean));
  const present = doc.lines.filter(line => standing.has(line)).length;
  if (present === doc.lines.length) return { unchanged: true };
  if (present) return { error: 'Some of these lines stand on main already and some do not.', status: 409, refused: 'duplicate' };
  const content = `${old}${doc.lines.join('\n')}\n`;
  if (Buffer.byteLength(content, 'utf8') > BIRTHS_FILE_MAX_BYTES) {
    return { error: `The births file would be over ${BIRTHS_FILE_MAX_BYTES} bytes.`, status: 413, refused: 'size' };
  }
  return { content };
}

/** The latest commit on `main` that touched `path`: `{ ok, commit, committed_at }` or `{ error, status }`. */
export async function lastCommit({ repo, token, path, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    const data = await github.get('file history', 'GET', `/commits?path=${encodeURIComponent(path)}&sha=${BASE}&per_page=1`);
    const top = Array.isArray(data) ? data[0] : null;
    const at = top?.commit?.committer?.date;
    if (!top || typeof at !== 'string' || Number.isNaN(Date.parse(at))) {
      return { error: 'GitHub named no commit of the births file.', status: 502, refused: 'github' };
    }
    return { ok: true, commit: needSha(top.sha, 'file history'), committed_at: at };
  } catch (error) {
    return refusal(error, token);
  }
}

/** Git's own id for a blob of this text: what GitHub's Contents API reports as a file's `sha`. */
export function blobSha(content) {
  const bytes = Buffer.from(content, 'utf8');
  return createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${bytes.length}\u0000`, 'utf8'), bytes])).digest('hex');
}

/**
 * What `main` holds at the path now: `{ ok, sha }` (`sha` null when there is no file) or `{ error, status }`. A
 * directory or a symlink at the path is refused: the route writes a plain file.
 */
export async function readDoc({ repo, token, path, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  try {
    const found = await github.ask('read file', 'GET', `/contents/${path}?ref=${BASE}`);
    if (found.status === 404) return { ok: true, sha: null };
    const data = github.need(found, 'read file');
    if (Array.isArray(data) || data.type !== 'file') return { error: 'The path holds something other than a file.', status: 409, refused: 'path' };
    return { ok: true, sha: needSha(data.sha, 'read file') };
  } catch (error) {
    return refusal(error, token);
  }
}

/**
 * Commit the admitted doc to `main` (`PUT /contents/<path>`), replacing the blob `sha` when there is one.
 * `{ committed: true, commit, blob }`, `{ committed: false, error, status }` when GitHub answered a definite no (a 4xx;
 * a 409 or 422 is a file that moved meanwhile: read it again), or `{ committed: null, error, status }` when nothing
 * answered or the answer was a 5xx: the commit may have been made, so the day's place stays taken.
 */
export async function putDoc({ repo, token, doc, sha = null, fetcher = fetch }) {
  const github = client({ repo, token, fetcher });
  let reply;
  try {
    reply = await github.ask('commit file', 'PUT', `/contents/${doc.path}`, {
      message: doc.message, content: Buffer.from(doc.content, 'utf8').toString('base64'), branch: BASE, ...(sha ? { sha } : {}),
    });
  } catch (error) {
    return { committed: null, ...refusal(error, token) };
  }
  if (reply.ok) {
    const commit = typeof reply.data?.commit?.sha === 'string' ? reply.data.commit.sha : null;
    const at = reply.data?.commit?.committer?.date;
    return {
      committed: true, commit, blob: typeof reply.data?.content?.sha === 'string' ? reply.data.content.sha : null,
      // GitHub's own time of the commit (R3: a birth's registration time is its receipt).
      committed_at: typeof at === 'string' && !Number.isNaN(Date.parse(at)) ? at : null,
    };
  }
  let error;
  try {
    github.need(reply, 'commit file');
  } catch (caught) {
    error = refusal(caught, token).error;
  }
  // Only a 4xx is GitHub's no; a 5xx may come after the commit was made, so it is no answer and the place stays taken.
  if (!definiteNo(reply.status)) return { committed: null, error, status: 502 };
  return { committed: false, error, status: reply.status === 409 || reply.status === 422 ? 409 : 502 };
}
