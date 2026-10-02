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

import { createHash } from 'node:crypto';
import { client, refused as refusal, sha as needSha, BASE } from './github.mjs';

export const DOCS_PATH = /^docs\/runs\/desk\/(\d{4})-(\d{2})-(\d{2})(-[a-z0-9-]+)?\.md$/;
export const DOCS_MAX_BYTES = 64 * 1024;
//: Commits a New York day. A constant: only the owner's deploy changes it.
export const DOCS_PER_DAY = 6;
export const DOCS_PREFIX = 'desk:';
export const MAX_MESSAGE_CHARS = 100;
//: The request: the file (escaped in JSON it can grow) and its message.
export const MAX_REQUEST_BYTES = 192 * 1024;
export const FOOTER = 'Committed by the House through the LTCM gateway (POST /v1/github/docs).';

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
 * `{ committed: true, commit, blob }`, `{ committed: false, error, status }` when GitHub answered no (a 409 or 422 is a
 * file that moved meanwhile: read it again), or `{ committed: null, error, status }` when nothing answered: the commit
 * may have been made, so the day's place stays taken.
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
    return { committed: true, commit, blob: typeof reply.data?.content?.sha === 'string' ? reply.data.content.sha : null };
  }
  let error;
  try {
    github.need(reply, 'commit file');
  } catch (caught) {
    error = refusal(caught, token).error;
  }
  return { committed: false, error, status: reply.status === 409 || reply.status === 422 ? 409 : 502 };
}
