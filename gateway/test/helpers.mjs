// Test material. Every key here is generated in-process for the test that uses it: this suite
// never reads a real credential, and there is nothing key-shaped in the repository to leak.

import { createHash, createPrivateKey } from 'node:crypto';

export const TOKEN = 'gateway-token-that-is-long-enough-1234567890';

export const pem = (label, der) =>
  `-----BEGIN ${label}-----\n${Buffer.from(der).toString('base64').match(/.{1,64}/g).join('\n')}\n-----END ${label}-----\n`;

/** An RSA-PSS SHA-256 key pair, as PKCS#8 PEM, PKCS#1 PEM and a verifying public key. */
export async function rsaKey() {
  const pair = await crypto.subtle.generateKey(
    { name: 'RSA-PSS', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    true, ['sign', 'verify'],
  );
  const pkcs8 = pem('PRIVATE KEY', await crypto.subtle.exportKey('pkcs8', pair.privateKey));
  return {
    pkcs8,
    pkcs1: createPrivateKey(pkcs8).export({ type: 'pkcs1', format: 'pem' }),
    publicKey: pair.publicKey,
  };
}

/** A `fetch` stand-in that records every call and replays one scripted reply. */
export function recorder(reply = { status: 200, body: '{"ok":true}' }) {
  const calls = [];
  const fetcher = async (url, options = {}) => {
    calls.push({ url: String(url), ...options });
    if (typeof reply === 'function') return reply(String(url), options);
    if (reply instanceof Error) throw reply;
    return new Response(reply.body ?? null, {
      status: reply.status ?? 200,
      headers: reply.headers ?? { 'Content-Type': 'application/json' },
    });
  };
  return { fetcher, calls };
}

/** A synchronous key/value store standing in for the Durable Object's SQLite table. */
export function memoryStore(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { get: key => map.get(key), set: (key, value) => map.set(key, value), map };
}

export const bearer = (extra = {}) => ({ Authorization: `Bearer ${TOKEN}`, ...extra });

export const GITHUB_REPO = 'bwoods1998/long-term-capital-management';
export const GITHUB_TOKEN = 'github_pat_TEST_token_that_never_leaves_the_worker';

const sha1 = value => createHash('sha1').update(typeof value === 'string' ? value : JSON.stringify(value)).digest('hex');

/**
 * A GitHub small enough to read: the Git Data and Pulls calls the gateway makes, answered from
 * state that behaves like git does. Blobs and trees are content-addressed, a commit is new every
 * time, a branch or an open pull request that exists is a 422. `script(key, init, body)` may
 * answer a call first (`key` is `METHOD /path` inside the repository); `moveMain()` lands a
 * commit on main the way a merged pull request would; `checks` is what CI reports.
 */
export function fakeGitHub({ script = () => undefined, checks = { total_count: 0, check_runs: [] } } = {}) {
  const calls = [];
  const reply = (status, data) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  const trees = new Map();   // sha -> { path: blob sha }
  const commits = new Map(); // sha -> tree sha
  const refs = new Map();    // branch -> commit sha
  const pulls = [];
  const plant = files => { const sha = sha1(Object.entries(files).sort()); trees.set(sha, files); return sha; };
  const commit = (tree, salt) => { const sha = sha1(['commit', tree, salt]); commits.set(sha, tree); return sha; };
  refs.set('main', commit(plant({ 'README.md': sha1('readme') }), 0));
  const state = { calls, refs, pulls, checks, moveMain() {
    const tree = plant({ ...trees.get(commits.get(refs.get('main'))), [`league/merged_${commits.size}.py`]: sha1(String(commits.size)) });
    refs.set('main', commit(tree, commits.size));
  } };

  state.fetcher = async (url, init = {}) => {
    const prefix = `https://api.github.com/repos/${GITHUB_REPO}`;
    const path = String(url).startsWith(prefix) ? String(url).slice(prefix.length) : String(url);
    const key = `${init.method} ${path}`;
    const body = init.body === undefined ? undefined : JSON.parse(init.body);
    calls.push({ url: String(url), key, method: init.method, headers: init.headers, body, redirect: init.redirect });
    const scripted = await script(key, init, body);
    if (scripted) return scripted;

    let match;
    if ((match = /^GET \/git\/ref\/heads\/(.+)$/.exec(key))) {
      const sha = refs.get(match[1]);
      return sha ? reply(200, { ref: `refs/heads/${match[1]}`, object: { type: 'commit', sha } }) : reply(404, { message: 'Not Found' });
    }
    if ((match = /^GET \/git\/commits\/([0-9a-f]+)$/.exec(key))) {
      return commits.has(match[1]) ? reply(200, { sha: match[1], tree: { sha: commits.get(match[1]) } }) : reply(404, { message: 'Not Found' });
    }
    if ((match = /^GET \/git\/trees\/([0-9a-f]+)\?recursive=1$/.exec(key))) {
      return reply(200, { sha: match[1], truncated: false, tree: Object.entries(trees.get(match[1]) || {}).map(([file, sha]) => ({ path: file, type: 'blob', sha })) });
    }
    if (key === 'POST /git/blobs') return reply(201, { sha: sha1(`blob ${body.content}`) });
    if (key === 'POST /git/trees') {
      const files = { ...trees.get(body.base_tree) };
      for (const entry of body.tree) files[entry.path] = entry.sha;
      return reply(201, { sha: plant(files) });
    }
    if (key === 'POST /git/commits') return reply(201, { sha: commit(body.tree, commits.size) });
    if (key === 'POST /git/refs') {
      const branch = body.ref.replace('refs/heads/', '');
      if (refs.has(branch)) return reply(422, { message: 'Reference already exists' });
      refs.set(branch, body.sha);
      return reply(201, { ref: body.ref, object: { sha: body.sha } });
    }
    const owner = GITHUB_REPO.split('/')[0];
    const shown = pull => ({ ...pull, head: { ref: pull.head, sha: refs.get(pull.head) } });
    if (key === 'POST /pulls') {
      if (pulls.some(pull => pull.head === body.head && pull.state === 'open')) {
        return reply(422, { message: 'Validation Failed', errors: [{ message: `A pull request already exists for ${owner}:${body.head}.` }] });
      }
      const number = 40 + pulls.length + 1;
      pulls.push({ number, state: 'open', merged: false, mergeable_state: 'clean', title: body.title, body: body.body, head: body.head, base: body.base,
        html_url: `https://github.com/${GITHUB_REPO}/pull/${number}` });
      return reply(201, shown(pulls.at(-1)));
    }
    if ((match = /^GET \/pulls\?(.+)$/.exec(key))) {
      const query = new URLSearchParams(match[1]);
      return reply(200, pulls.filter(pull => `${owner}:${pull.head}` === query.get('head') && pull.state === query.get('state')).map(shown));
    }
    if ((match = /^GET \/pulls\/(\d+)$/.exec(key))) {
      const pull = pulls.find(row => row.number === Number(match[1]));
      return pull ? reply(200, shown(pull)) : reply(404, { message: 'Not Found' });
    }
    if (/^GET \/commits\/[0-9a-f]+\/check-runs\?per_page=100$/.test(key)) return reply(200, state.checks);
    return reply(404, { message: `unscripted: ${key}` });
  };
  return state;
}


/**
 * The real Alpaca account as the gateway reads it (Sept 26, 2026 (the options-swarm run, Wave 5)). `GET v2/account`
 * answers `account` (a body, an HTTP status, or an Error to throw), `GET v2/positions` answers `positions` (the same),
 * and any other call is an accepted order. `orders()`, `accountReads()` and `positionReads()` split `calls`.
 */
export function alpacaVenue({ equity = '5000.00', account = { equity, status: 'ACTIVE' }, positions = [], order = { id: 'o-1', status: 'accepted' } } = {}) {
  const calls = [];
  const answer = value => {
    if (value instanceof Error) return Promise.reject(value);
    if (typeof value === 'number') return new Response('{}', { status: value, headers: { 'Content-Type': 'application/json' } });
    return new Response(typeof value === 'string' ? value : JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  const isAccount = url => url.endsWith('/v2/account');
  const isPositions = url => url.endsWith('/v2/positions');
  const fetcher = async (url, init = {}) => {
    calls.push({ url: String(url), ...init });
    if (isAccount(String(url))) return answer(account);
    if (isPositions(String(url))) return answer(positions);
    return answer(order);
  };
  return {
    fetcher, calls,
    orders: () => calls.filter(c => !isAccount(c.url) && !isPositions(c.url)),
    accountReads: () => calls.filter(c => isAccount(c.url)),
    positionReads: () => calls.filter(c => isPositions(c.url)),
  };
}

/** A gate holding a fresh reading of the real account's equity (`usd` dollars, read `ageMs` before `at`). */
export function withEquity(gate, usd = '5000.00', at = Date.now(), ageMs = 0) {
  const [whole, fraction = ''] = String(usd).split('.');
  gate.recordAccountEquity({ ok: true, at: at - ageMs, equity_micro: String(BigInt(whole) * 1000000n + BigInt(fraction.padEnd(6, '0').slice(0, 6))) });
  return gate;
}
