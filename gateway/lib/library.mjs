// The research library (Sept 29, 2026): literature posted BEFORE 2025, read from arXiv by this Worker for the swarm.
//
// WHY A LIBRARY AND NOT THE WEB. The agents should research as a trading firm's analysts do, but open web access would
// let them read about the Validation year (2025) and the sealed holdout (2026) and select on them, which fakes the
// verifier. So the swarm gets a LIBRARY: research literature dated before 2025-01-01, and nothing else. The rule is
// enforced HERE, on every answer, and again by the House (league/swarm/library.py); the prompts only describe it.
//
// THE DATE RULE. An item is served only if both its first-posted date (arXiv `published`, the v1 submission time) and
// the date of the version served (`updated` of that version) are before CUTOFF, in UTC, from arXiv's own metadata.
//   - A paper is served as it stood at the end of 2024: the NEWEST version dated before CUTOFF (`newestBefore`), pinned.
//     Every version posted from now on is dated after CUTOFF, so that version never changes (kept in KV as `e:`). A
//     search and an unversioned read both serve it; a read that names a version serves that version only when it is
//     itself before CUTOFF, and answers a later one exactly as a version that does not exist (`not_found`), so no answer
//     shows whether, or how often, a paper was revised after 2024 (review of #428, look-ahead F3).
//   - A search matches titles and abstracts only (`ti:`/`abs:`, never `all:`, which also searches comments and journal
//     references an author can add without a new version: review of #428, look-ahead F1). arXiv matches the LATEST
//     version, so a paper revised after 2024 is kept only when EVERY query term is in the served version's own title or
//     abstract (`matchesTerms`, plurals folded as arXiv's stemmer does); else words added after 2024 would choose it.
//     What remains: arXiv's relevance ORDER among the admitted items is computed on the latest text, and a paper's
//     categories are its current ones (a cross-listing added after 2024 can move it into the library's topics).
//   - A missing or unparseable date, dates that disagree (updated before published), or a new-style id whose YYMM is
//     2501 or later whatever its dates say, is refused (`no_reliable_date`).
//   - Every item served is PINNED to a version (`arXiv:<base>v<N>`); a pinned version never changes, so a cached one
//     stays valid. Nothing unversioned is ever served.
//   - Every text served (titles, abstracts, full text) passes the post-cutoff date scan (`POST_CUTOFF`): in pinned text
//     (the API's abstracts, arXiv's own version-pinned HTML) a match -- a forecast, a bond's maturity -- becomes
//     "[date]"; in ar5iv's text, which is not pinned to a version, any match withholds the whole text.
//   - CUTOFF is a constant in code, never a setting or a var: it is a rule of the verifier (D2), not throughput. It is
//     mirrored in league/swarm/library.py, and tests pin both.
//   - What was withheld is counted in `withheld` for the House's own log; the House drops it before a model sees
//     anything, so no count of post-2024 work reaches an agent.
//
// THE SOURCES, and only these three hosts (`checkLibraryUrl`; every upstream URL is built here from validated parts):
//   - https://export.arxiv.org/api/query   arXiv's API (Atom): search, and metadata by id (`id_list=<base>v<N>` answers
//                                          that version's own dates, title and abstract);
//   - https://arxiv.org/html/<base>v<N>    arXiv's own HTML, pinned to a version (from about December 2023 on; not
//                                          every paper has one). Only its <article> is read: the page's chrome holds
//                                          later years;
//   - https://ar5iv.labs.arxiv.org/html/<base>  LaTeXML renderings of older papers, NOT pinned to a version: read only
//                                          when the served version is the paper's latest and that latest is before
//                                          CUTOFF (so every version is), with the latest re-read within the hour.
//   PDFs are not parsed (a dependency, and CPU in the isolate that serves orders): an item with no HTML is its
//   metadata and abstract (`text_source: "none"`). Redirects are followed by hand, at most MAX_REDIRECTS, each hop
//   checked and paced like a request, and only to the SAME item (`fetchPaced`'s `expect`: the same API query, the same
//   paper and version on arxiv.org/html, the same paper on ar5iv at no version past its confirmed latest), so no
//   redirect can serve another version's text under this one's id (review of #428, look-ahead F2). No URL names a
//   new-style id after 2412. The only headers sent are a fixed User-Agent and Accept; no secret is needed.
//
// ARXIV'S TERMS (info.arxiv.org/help/api/tou.html, read Sept 29, 2026): "make no more than one request every three
// seconds, and limit requests to a single connection at a time", for "all of the machines under your control as a
// whole"; arxiv.org's robots.txt sets `Crawl-delay: 15`. So one arXiv request at a time across all three hosts, each
// host's starts SPACING_MS apart (3 s for the API and ar5iv, 15 s for arxiv.org), a backoff of at least BACKOFF_MS
// when arXiv answers 403, 429 or 503 (a 403 is how a blocked address is told), and at most LIBRARY_DAY_UPSTREAM
// requests a UTC day (600 by default, about 2% of what the terms allow). The pace, the lease and the day's count live in the Gate (`libraryAcquire`, `libraryRelease`: two
// small synchronous transactions, the `webFetchReserve` pattern; no new Durable Object class, which would end
// `wrangler rollback` for the gateway that carries real orders). No upstream request starts later than REQUEST_BUDGET_MS
// after the library request came in; one that cannot is `429 {busy: true}` with nothing sent and nothing counted. So a
// library request takes at most WORST_MS (the budget plus one fetch's timeout), which the House's client outwaits. Metadata is CC0; e-print text is read for our
// own research and served only to the authenticated House, never published (never an event, never the site, never
// git), and its cache expires.
//
// THE CACHE is the KV namespace bound as LIBRARY (the Cache API works on custom domains only, and this Worker is on
// workers.dev). Without the binding the library works uncached, still paced and counted. Every cached item is admitted
// again on the way out, so a bad write is never served. `X-LTCM-Library: hit|miss` says which.
//
// THE ROUTES (GET only, the runtime bearer token; they move no money, so the kill switch does not stop them):
//   /v1/research/search?q=&cat=&max=   up to `max` items (ITEM below) for plain keywords;
//   /v1/research/read?id=&start=&chars= one pinned version's metadata and a window of its text;
//   /v1/research/health                 the pace, the lease and the day's count (also `library` in /v1/health).
// ITEM: {id: "arXiv:<base>v<N>", title, authors (at most six, then "et al."), first_posted, version, version_date,
// primary_category, categories, abstract, url}. Comments, journal references and DOIs are never read: they belong to
// the latest version, and a comment may hold personal data.

import { json } from './http.mjs';
import { htmlToText, decodeEntities, readCapped, decode, cut, discard } from './fetch.mjs';

// --- the rule ----------------------------------------------------------------------------------------------------------

//: The date rule's line: an item and the version served must both be dated before it. A constant, never a setting.
export const CUTOFF = '2025-01-01T00:00:00Z';
export const CUTOFF_MS = Date.UTC(2025, 0, 1);
//: The last day the library serves, as its answers say it (a post-cutoff date never appears in an answer).
export const LAST_DAY = '2024-12-31';
//: New-style ids (YYMM.NNNNN) name their month: 2412 is the last the rule admits.
export const LAST_YYMM = 2412;

const YEAR = '(?:20(?:2[5-9]|[3-9][0-9]))';
const MONTH = '(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?'
  + '|nov(?:ember)?|dec(?:ember)?)\\.?';
//: A date on or after 2025-01-01 written in text (years 2025-2099): ISO dates, "Month [D,] YYYY", "D Month YYYY", "Q1 2025",
//: "2025Q1", "FY2025", "(2025)", a year after in, by, during, since, until, till, through, from, before, after, year,
//: fiscal, early, late or mid, "the end (start, summer, ...) of 2025", "as of 2025", and a new-style arXiv id of 2501 or
//: later. Bare numbers ("n = 2048", "pp. 2037-2053", "a strike of 2050") are left alone. league/swarm/library.py holds the
//: same pattern; gateway/test/library-date-cases.json is the case list both are tested against.
export const POST_CUTOFF_SOURCE = [
  `(?<![0-9])${YEAR}[-/](?:0?[1-9]|1[0-2])(?:[-/](?:0?[1-9]|[12][0-9]|3[01]))?(?![0-9])`,
  `\\b${MONTH}\\s+(?:[0-9]{1,2}(?:st|nd|rd|th)?,?\\s+)?${YEAR}(?![0-9])`,
  `(?<![0-9])[0-9]{1,2}(?:st|nd|rd|th)?\\s+${MONTH},?\\s+${YEAR}(?![0-9])`,
  `\\bQ[1-4]\\s?[-/]?\\s?${YEAR}(?![0-9])`,
  `(?<![0-9])${YEAR}\\s?[-/]?\\s?Q[1-4]\\b`,
  `\\bFY\\s?[-']?\\s?${YEAR}(?![0-9])`,
  `\\(\\s*${YEAR}[a-z]?\\s*\\)`,
  `\\b(?:in|by|during|since|until|till|through|from|before|after|year|years|fiscal|early|late|mid)[\\s-]+${YEAR}(?![0-9])`,
  `\\b(?:end|start|beginning|middle|half|quarter|summer|winter|spring|autumn|fall|as)\\s+of\\s+${YEAR}(?![0-9])`,
  '(?<![0-9.])(?:2[5-9]|[3-9][0-9])(?:0[1-9]|1[0-2])\\.[0-9]{4,5}(?![0-9])',
].join('|');
const POST_CUTOFF_ALL = new RegExp(POST_CUTOFF_SOURCE, 'gi');
export const POST_CUTOFF = new RegExp(POST_CUTOFF_SOURCE, 'i');

/** True when `text` names a date on or after the cutoff. */
export const hasPostCutoff = text => typeof text === 'string' && POST_CUTOFF.test(text);

/** Pinned text with every post-cutoff date replaced by "[date]"; null when one cannot be removed. */
export function scrubDates(text) {
  if (typeof text !== 'string') return null;
  let out = text;
  for (let pass = 0; pass < 3 && POST_CUTOFF.test(out); pass++) out = out.replace(POST_CUTOFF_ALL, '[date]');
  return POST_CUTOFF.test(out) ? null : out;
}

const LOCAL_CHAR = /[A-Za-z0-9._%+-]/;
const DOMAIN_CHAR = /[A-Za-z0-9.-]/;

/**
 * Every email address in `text` as "[email]": papers print their authors' addresses, and the library passes no personal
 * data on. One forward pass from each "@" (a pattern like `[\w.]+@` is quadratic on a long run of letters).
 */
export function redactEmails(text) {
  if (typeof text !== 'string' || !text.includes('@')) return text;
  let out = '';
  let last = 0;
  for (let at = text.indexOf('@'); at !== -1; at = text.indexOf('@', at + 1)) {
    let left = at;
    while (left > last && LOCAL_CHAR.test(text[left - 1])) left--;
    let right = at + 1;
    while (right < text.length && DOMAIN_CHAR.test(text[right])) right++;
    while (right > at + 1 && (text[right - 1] === '.' || text[right - 1] === '-')) right--;
    if (left < at && /\.[A-Za-z]{2,}$/.test(text.slice(at + 1, right))) {
      out += text.slice(last, left) + '[email]';
      last = right;
      at = right - 1;
    }
  }
  return out + text.slice(last);
}

// --- the sources and the pace ------------------------------------------------------------------------------------------

export const API_HOST = 'export.arxiv.org';
export const HTML_HOST = 'arxiv.org';
export const AR5IV_HOST = 'ar5iv.labs.arxiv.org';
export const HOSTS = [API_HOST, HTML_HOST, AR5IV_HOST];
//: Starts on one host at least this far apart: the API's terms (one request every three seconds), arxiv.org's robots.txt
//: (Crawl-delay: 15), and ar5iv at the API's pace (its robots.txt names no delay).
export const SPACING_MS = { [API_HOST]: 3000, [HTML_HOST]: 15000, [AR5IV_HOST]: 3000 };
//: How long one upstream request may take; a lease no worker released expires at its start plus this plus LEASE_SLACK_MS.
export const FETCH_TIMEOUT_MS = { [API_HOST]: 10000, [HTML_HOST]: 15000, [AR5IV_HOST]: 15000 };
export const LEASE_SLACK_MS = 5000;
//: The least pause after arXiv answers one of BACKOFF_STATUSES (longer when its Retry-After says so).
export const BACKOFF_MS = 60000;
//: arXiv's answers that start a backoff: 429 and 503 ask us to slow down, and a 403 is how a blocked address is told
//: (review of #428, gateway F3: without it a block was hit at full pace up to the day's cap).
export const BACKOFF_STATUSES = [403, 429, 503];
//: No upstream request starts later than this after the library request came in; one that cannot is `429 {busy: true}`
//: with nothing sent or counted.
export const REQUEST_BUDGET_MS = 20000;
//: The longest a library request takes (the budget, then one fetch at the longest timeout). The House's client waits at
//: least this plus a margin (league/swarm/library.py CLIENT_FLOOR_SECONDS), so it never abandons a request mid-flight:
//: an abandoned request can leave its lease held and its in-flight place taken (review of #428, gateway F7).
export const WORST_MS = REQUEST_BUDGET_MS + 15000;
//: The longest single sleep between two asks of the Gate.
export const POLL_MS = 3000;
//: Upstream requests a UTC day, the whole floor (LIBRARY_DAY_UPSTREAM overrides it; 0 stops every request to arXiv,
//: while cache hits still answer).
export const DAY_UPSTREAM = 600;
const DAY_UPSTREAM_MAX = 20000;
//: Library requests one isolate serves at once (the isolate that serves the order routes holds their bodies).
export const MAX_IN_FLIGHT = 4;
export const MAX_REDIRECTS = 2;
export const MAX_FEED_BYTES = 1024 * 1024;
export const MAX_PAGE_BYTES = 3 * 1024 * 1024;
export const MAX_TEXT_CHARS = 300_000;
export const MAX_ABSTRACT_CHARS = 2000;
export const MAX_TITLE_CHARS = 400;
export const MAX_AUTHORS = 6;
export const MAX_SECTIONS = 40;
//: Headings an article's scan looks at, found or not (each costs a search of the text): a hostile page of thousands of
//: empty or unmatched headings stays cheap in the isolate that serves orders.
export const MAX_HEADINGS = 3 * MAX_SECTIONS;
//: A paper's versions one batched metadata call may ask for, and one search's batch in all (a feed of about 3 KB an
//: entry stays well under MAX_FEED_BYTES).
export const MAX_VERSIONS = 60;
export const MAX_BATCH_IDS = 100;
export const READ_CHARS = 8000;
export const MAX_READ_CHARS = 10000;
//: arXiv's own HTML exists for papers from about December 2023 on: an older version is not asked for it.
export const HTML_SINCE_MS = Date.UTC(2023, 11, 1);
//: ar5iv is read only while the paper's latest version was confirmed this recently.
export const LATEST_FRESH_MS = 3600000;
//: KV lifetimes, in seconds: a search answer, a pinned version's metadata, a paper's latest version, its text, "no text",
//: and the paper's newest version before the cutoff (`e:`: it never changes, as every later version is after it).
export const TTL = { search: 7 * 86400, meta: 180 * 86400, latest: 7 * 86400, text: 30 * 86400, none: 7 * 86400, best: 180 * 86400 };
export const USER_AGENT = 'LTCM-library/1.0 (+https://blakewoods.us/capital)';
export const PATHS = { search: '/v1/research/search', read: '/v1/research/read', health: '/v1/research/health' };
export const CACHE_HEADER = 'X-LTCM-Library';

/** The day's upstream cap from LIBRARY_DAY_UPSTREAM (a whole number, 0 to 20,000), else DAY_UPSTREAM. */
export function dayCap(env = {}) {
  const raw = env.LIBRARY_DAY_UPSTREAM;
  const value = raw === undefined || raw === null || raw === '' ? NaN : Number(raw);
  return Number.isInteger(value) && value >= 0 && value <= DAY_UPSTREAM_MAX ? value : DAY_UPSTREAM;
}

// --- ids ---------------------------------------------------------------------------------------------------------------

const NEW_BASE = '[0-9]{4}\\.[0-9]{4,5}';
const OLD_BASE = '[a-z][a-z-]{0,19}(?:\\.[A-Za-z-]{2,12})?/[0-9]{7}';
const BASE = `(?:${NEW_BASE}|${OLD_BASE})`;
const ID = new RegExp(`^(?:arxiv:)?(${BASE})(?:v([1-9][0-9]{0,2}))?$`, 'i');

/** `{ base, version (a number or null), yymm (new-style) }` for an arXiv id as an agent may write it, or null. */
export function parseId(raw) {
  if (typeof raw !== 'string') return null;
  const text = raw.trim();
  if (!text || text.length > 60) return null;
  const match = ID.exec(text);
  if (!match) return null;
  const base = /^[0-9]/.test(match[1]) ? match[1] : match[1].replace(/^[A-Za-z-]+/, s => s.toLowerCase());
  const yymm = /^[0-9]{4}\./.test(base) ? Number(base.slice(0, 4)) : null;
  if (yymm !== null && (yymm % 100 < 1 || yymm % 100 > 12)) return null;
  return { base, version: match[2] ? Number(match[2]) : null, yymm };
}

/** True for an id whose own name says it is after the cutoff (a new-style YYMM of 2501 or later). */
export const idAfterCutoff = parsed => parsed.yymm !== null && parsed.yymm > LAST_YYMM;

// --- the allowlist -----------------------------------------------------------------------------------------------------

const HTML_PATH = new RegExp(`^/html/(${BASE})v[1-9][0-9]{0,2}/?$`);
const AR5IV_PATH = new RegExp(`^/html/(${BASE})(?:v[1-9][0-9]{0,2})?/?$`);

/** True when a page path's paper is one the rule may read: a valid id whose own name is not after the cutoff. */
const pathPaper = (pattern, pathname) => {
  const match = pattern.exec(pathname);
  const parsed = match && parseId(match[1]);
  return Boolean(parsed) && !idAfterCutoff(parsed);
};

/**
 * `{ ok: true, url, host }` for one of the three shapes the library reads, else `{ ok: false, error }`: exactly
 * https://export.arxiv.org/api/query?..., https://arxiv.org/html/<base>v<N> (the version is required) and
 * https://ar5iv.labs.arxiv.org/html/<base>; no port, user, fragment, other host or path, and no page of a new-style id
 * after 2412 (review of #428, look-ahead F2). Checked before every fetch and on every redirect's target, where
 * `fetchPaced`'s `expect` also holds the target to the same item.
 */
export function checkLibraryUrl(raw) {
  if (typeof raw !== 'string' || raw.length > 4096) return { ok: false, error: 'not a url' };
  let url;
  try {
    url = new URL(raw);
  } catch {
    return { ok: false, error: 'the url cannot be parsed' };
  }
  if (url.protocol !== 'https:') return { ok: false, error: 'only https is read' };
  if (url.username || url.password || url.port !== '' || url.hash) return { ok: false, error: 'no user, port or fragment' };
  const host = url.hostname;
  if (host === API_HOST) {
    return url.pathname === '/api/query' && url.search.length > 1 ? { ok: true, url, host } : { ok: false, error: 'only /api/query' };
  }
  if (host === HTML_HOST) {
    return pathPaper(HTML_PATH, url.pathname) && !url.search ? { ok: true, url, host } : { ok: false, error: 'only /html/<id>v<N> before 2501' };
  }
  if (host === AR5IV_HOST) {
    return pathPaper(AR5IV_PATH, url.pathname) && !url.search ? { ok: true, url, host } : { ok: false, error: 'only /html/<id> before 2501' };
  }
  return { ok: false, error: 'not a library host' };
}

// --- the query ---------------------------------------------------------------------------------------------------------

export const CATEGORIES = ['all', 'q-fin', 'econ', 'stat.ML', 'cs.LG'];
//: "cs.LG where it concerns markets": the words one of which a cs.LG item must hold.
export const MARKET_WORDS = ['market', 'markets', 'trading', 'option', 'options', 'volatility', 'portfolio', 'financial',
  'finance', 'asset', 'stock', 'price'];
/** A term matched in a title or an abstract only: `all:` would also search comments and journal references, which an
 * author can change without a new version, so no date the rule checks would move (review of #428, look-ahead F1). */
export const inTitleOrAbstract = term => {
  const field = term.includes(' ') ? `"${term}"` : term;
  return `(ti:${field} OR abs:${field})`;
};
const CAT_CLAUSE = {
  'q-fin': 'cat:q-fin.*',
  econ: 'cat:econ.*',
  'stat.ML': 'cat:stat.ML',
  'cs.LG': `(cat:cs.LG AND (${MARKET_WORDS.map(w => `ti:${w} OR abs:${w}`).join(' OR ')}))`,
};
CAT_CLAUSE.all = `(${['q-fin', 'econ', 'stat.ML', 'cs.LG'].map(k => CAT_CLAUSE[k]).join(' OR ')})`;
//: arXiv's v1 filter, a pre-filter only: `updated` decides per entry (the API silently rewrites lastUpdatedDate into
//: submittedDate, so no filter on the version date exists).
export const DATE_CLAUSE = 'submittedDate:[199101010000 TO 202412312359]';
export const MAX_TERMS = 8;
//: arXiv's operators and a few stopwords: never a term.
const DROPPED_WORDS = new Set(['and', 'or', 'not', 'andnot', 'the', 'an', 'of', 'in', 'on', 'to', 'for', 'with', 'by', 'at', 'from',
  'is', 'are']);
//: A word that holds a year from 2025 on ("2025", "fy2026", "202501010000"): dropped whole.
const YEAR_WORD = /(?<![0-9])20(?:2[5-9]|[3-9][0-9])/;

/** A token's words: lower case, apostrophes dropped, hyphens split; no operator, stopword or year from 2025 on. */
function wordsOf(text) {
  return text.toLowerCase().replace(/'/g, '').split(/[\s-]+/)
    .filter(w => w.length >= 2 && w.length <= 40 && !DROPPED_WORDS.has(w) && !YEAR_WORD.test(w));
}

/**
 * The arXiv query for an agent's keywords. Nothing of `q` passes through raw: quoted phrases are kept; every other
 * word is a term; every character outside letters, digits, spaces, `-`, `'` and `"` is removed (no `:`, brackets,
 * parentheses or field prefixes reach arXiv); AND, OR and ANDNOT are removed, and so is every year from 2025 on; at most
 * MAX_TERMS terms. Each term is `(ti:<term> OR abs:<term>)`, ANDed; the category clause and DATE_CLAUSE are always
 * added. `{ query, terms, cat }` or `{ error }`.
 */
export function buildQuery(q, cat = 'all') {
  if (typeof q !== 'string') return { error: 'q (plain keywords) is required.' };
  const raw = q.trim();
  if (raw.length < 2 || raw.length > 200) return { error: 'q must be 2 to 200 characters of plain keywords.' };
  if (!CATEGORIES.includes(cat)) return { error: `cat must be one of ${CATEGORIES.join(', ')}.` };
  const clean = raw.replace(/[^A-Za-z0-9 \-'"]/g, ' ');
  const parts = clean.split('"');
  const closed = parts.length % 2 === 1;
  const terms = [];
  const add = term => { if (!terms.includes(term) && terms.length < MAX_TERMS) terms.push(term); };
  parts.forEach((part, i) => {
    const quoted = i % 2 === 1 && (closed || i < parts.length - 1);
    if (quoted) {
      const words = wordsOf(part);
      if (words.length) add(words.join(' '));
      return;
    }
    for (const token of part.split(/\s+/)) {
      const words = wordsOf(token);
      if (words.length) add(words.join(' '));
    }
  });
  if (!terms.length) return { error: 'q has no searchable words (plain keywords; no years from 2025 on).' };
  return { query: `${CAT_CLAUSE[cat]} AND (${terms.map(inTitleOrAbstract).join(' AND ')}) AND ${DATE_CLAUSE}`, terms, cat };
}

const apiUrl = params => `https://${API_HOST}/api/query?${new URLSearchParams(params).toString()}`;
export const searchUrl = (query, n) => apiUrl({ search_query: query, start: '0', max_results: String(n), sortBy: 'relevance',
  sortOrder: 'descending' });
export const idsUrl = ids => apiUrl({ id_list: ids.join(','), max_results: String(ids.length) });

// --- the feed ----------------------------------------------------------------------------------------------------------

/** Where the next `<name>` or `<name ...>` tag opens in `text` at or after `from`, or -1. */
function openAt(text, name, from) {
  let at = from;
  for (;;) {
    const open = text.indexOf(`<${name}`, at);
    if (open === -1) return -1;
    const after = text.charCodeAt(open + name.length + 1);
    if (after === 62 || after === 32 || after === 47 || after === 10 || after === 9 || after === 13) return open;
    at = open + 1;
  }
}

/** The first `<name>` element in `block` at or after `from` (an Atom entry is flat): its text, its opening tag and where it
 * ends; null when there is none or it never closes. Linear: indexOf only. */
function element(block, name, from = 0) {
  const open = openAt(block, name, from);
  if (open === -1) return null;
  const end = block.indexOf('>', open);
  if (end === -1) return null;
  if (block.charCodeAt(end - 1) === 47) return { text: '', end: end + 1, tag: block.slice(open, end + 1) };
  const close = block.indexOf(`</${name}>`, end);
  if (close === -1) return null;
  return { text: block.slice(end + 1, close), end: close + name.length + 3, tag: block.slice(open, end + 1) };
}

/** Every `<name .../>` or `<name>...</name>` element in `block`. */
function elements(block, name) {
  const out = [];
  let at = 0;
  for (let found = element(block, name, at); found; found = element(block, name, at)) {
    out.push(found);
    at = found.end;
  }
  return out;
}

const attribute = (tag, name) => {
  const at = tag.indexOf(` ${name}="`);
  if (at === -1) return null;
  const end = tag.indexOf('"', at + name.length + 3);
  return end === -1 ? null : tag.slice(at + name.length + 3, end);
};
const words = text => decodeEntities(String(text || '')).replace(/\s+/g, ' ').trim();
const CATEGORY = /^[A-Za-z-]{1,20}(?:\.[A-Za-z-]{1,20})?$/;
const ABS = new RegExp(`^https?://arxiv\\.org/abs/(${BASE})v([1-9][0-9]{0,2})$`);
const ERRORS = /^https?:\/\/arxiv\.org\/api\/errors/;

/** One entry's fields (never its comment, journal reference or DOI), or `{ error }` for an API error entry. */
function parseEntry(block) {
  const id = words(element(block, 'id')?.text);
  if (ERRORS.test(id)) return { error: words(element(block, 'summary')?.text).slice(0, 300) || 'an API error' };
  const abs = ABS.exec(id);
  const categories = elements(block, 'category').map(e => attribute(e.tag, 'term')).filter(t => t && CATEGORY.test(t));
  const primary = attribute(element(block, 'arxiv:primary_category')?.tag || '', 'term');
  return {
    base: abs ? abs[1] : null,
    version: abs ? Number(abs[2]) : null,
    title: words(element(block, 'title')?.text),
    summary: words(element(block, 'summary')?.text),
    published: words(element(block, 'published')?.text),
    updated: words(element(block, 'updated')?.text),
    authors: elements(block, 'author').map(a => words(element(a.text, 'name')?.text)).filter(Boolean),
    categories: [...new Set(categories)].slice(0, 16),
    primary: primary && CATEGORY.test(primary) ? primary : (categories[0] || null),
  };
}

/**
 * An Atom feed from arXiv's API: `{ ok: true, entries }`, or `{ ok: false, error, api_error }` for a feed that is not
 * one, is cut off, or is an API error. One forward pass with indexOf; never throws.
 */
export function parseFeed(xml) {
  if (typeof xml !== 'string' || !xml.includes('<feed')) return { ok: false, error: 'arXiv did not answer with an Atom feed' };
  const entries = [];
  for (let at = openAt(xml, 'entry', 0); at !== -1; at = openAt(xml, 'entry', at)) {
    const found = element(xml, 'entry', at);
    if (!found) return { ok: false, error: 'arXiv\'s feed was cut off inside an entry' };
    entries.push(parseEntry(found.text));
    at = found.end;
  }
  if (!xml.includes('</feed>')) return { ok: false, error: 'arXiv\'s feed was cut off' };
  const failed = entries.find(e => e.error);
  if (failed) return { ok: false, error: `arXiv refused the request: ${failed.error}`, api_error: true };
  return { ok: true, entries };
}

// --- admission ---------------------------------------------------------------------------------------------------------

const STAMP = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,9})?Z$/;

/** Milliseconds for an RFC 3339 UTC stamp as arXiv writes it, or null. */
export function stampMs(text) {
  const match = STAMP.exec(String(text || ''));
  if (!match) return null;
  const [y, mo, d, h, mi, s] = match.slice(1).map(Number);
  const ms = Date.UTC(y, mo - 1, d, h, mi, s);
  const back = new Date(ms);
  return back.getUTCFullYear() === y && back.getUTCMonth() === mo - 1 && back.getUTCDate() === d ? ms : null;
}

/**
 * What the rule makes of one version's entry: 'ok', 'revised' (first posted before the cutoff, this version on or
 * after it: its v1 may be served instead), 'after_cutoff', or 'no_reliable_date'.
 */
export function judge(entry) {
  if (!entry || !entry.base || !entry.version) return 'no_reliable_date';
  const parsed = parseId(entry.base);
  const published = stampMs(entry.published);
  const updated = stampMs(entry.updated);
  if (!parsed || published === null || updated === null || updated < published) return 'no_reliable_date';
  if (published >= CUTOFF_MS) return 'after_cutoff';
  if (idAfterCutoff(parsed)) return 'no_reliable_date';  // a 2501+ id whose dates claim 2024: the metadata disagrees
  if (updated >= CUTOFF_MS) return 'revised';
  return 'ok';
}

/** The allowed groups: q-fin.*, econ.*, stat.ML, and cs.LG where the item concerns markets. */
export function onTopic(entry) {
  const cats = entry.categories || [];
  if (cats.some(c => c.startsWith('q-fin.') || c.startsWith('econ.') || c === 'stat.ML')) return true;
  if (!cats.includes('cs.LG')) return false;
  const text = `${entry.title} ${entry.summary}`.toLowerCase();
  return MARKET_WORDS.some(w => new RegExp(`\\b${w}\\b`).test(text));
}

/** A word with an English plural folded ("options" -> "option", "volatilities" -> "volatility", "indexes" -> "index"),
 * as arXiv's stemmer folds it; "analysis", "gross" and "bonus" stay. The same fold on both sides of a comparison. */
export function fold(word) {
  if (word.length > 4 && word.endsWith('ies')) return `${word.slice(0, -3)}y`;
  if (word.length > 3 && /(?:ss|us|is)$/.test(word)) return word;
  if (word.length > 4 && /(?:ches|shes|sses|xes|zes)$/.test(word)) return word.slice(0, -2);
  if (word.length > 3 && word.endsWith('s')) return word.slice(0, -1);
  return word;
}

/** `text` as folded words, spaced: lower case, apostrophes dropped, every other non-alphanumeric a space. */
const foldedWords = text => String(text || '').toLowerCase().replace(/['\u2019]/g, '').split(/[^a-z0-9]+/).filter(Boolean).map(fold);

/**
 * True when EVERY query term (a word, or a phrase as consecutive words) is in the entry's own title or abstract, plurals
 * folded. The test for a paper revised after 2024 that is served as an earlier version: arXiv matched its LATEST text,
 * so a term only a later version holds must not choose it (review of #428, look-ahead F1: one term was enough before).
 */
export function matchesTerms(entry, terms) {
  const text = ` ${foldedWords(`${entry.title} ${entry.summary}`).join(' ')} `;
  return Array.isArray(terms) && terms.length > 0 && terms.every(term => {
    const words = foldedWords(term);
    return words.length > 0 && text.includes(` ${words.join(' ')} `);
  });
}

/** An admitted entry as the library answers it (`ITEM`), its texts scrubbed; null when a text cannot be. */
export function itemOf(entry) {
  const authors = entry.authors.slice(0, MAX_AUTHORS).map(scrubDates);
  const title = scrubDates(cut(entry.title, MAX_TITLE_CHARS));
  const abstract = scrubDates(redactEmails(cut(entry.summary, MAX_ABSTRACT_CHARS)));
  if (title === null || abstract === null || authors.includes(null)) return null;
  if (entry.authors.length > MAX_AUTHORS) authors.push('et al.');
  return admitItem({
    id: `arXiv:${entry.base}v${entry.version}`, title, authors, first_posted: entry.published.slice(0, 10), version: entry.version,
    version_date: entry.updated.slice(0, 10), primary_category: entry.primary, categories: entry.categories, abstract,
    url: `https://arxiv.org/abs/${entry.base}v${entry.version}`,
  });
}

const DAY = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const ITEM_KEYS = ['id', 'title', 'authors', 'first_posted', 'version', 'version_date', 'primary_category', 'categories', 'abstract', 'url'];

/**
 * An item (fresh or from the cache) admitted again: a pinned id that names no month after the cutoff, both dates
 * well-formed and before the cutoff, the version the id's, and no post-cutoff date anywhere in it. Null otherwise.
 */
export function admitItem(item) {
  if (!item || typeof item !== 'object') return null;
  const match = /^arXiv:(.+)v([1-9][0-9]{0,2})$/.exec(String(item.id || ''));
  const parsed = match && parseId(match[1]);
  if (!parsed || parsed.base !== match[1] || idAfterCutoff(parsed) || Number(match[2]) !== item.version) return null;
  if (!DAY.test(item.first_posted) || !DAY.test(item.version_date)) return null;
  if (!(item.first_posted < '2025-01-01') || !(item.version_date < '2025-01-01') || item.version_date < item.first_posted) return null;
  if (!Array.isArray(item.authors) || !Array.isArray(item.categories)) return null;
  const clean = Object.fromEntries(ITEM_KEYS.map(k => [k, item[k]]));
  return hasPostCutoff(JSON.stringify(clean)) ? null : clean;
}

// --- full text ---------------------------------------------------------------------------------------------------------

/** The page's first `<article ...>` element (LaTeXML's document), or null. `partial` (a page cut at MAX_PAGE_BYTES):
 * an article that never closes is read to the end of what arrived. */
export function articleOf(html, { partial = false } = {}) {
  let at = 0;
  for (;;) {
    const open = html.indexOf('<article', at);
    if (open === -1) return null;
    const next = html.charCodeAt(open + 8);
    if (next === 62 || next === 32 || next === 10 || next === 9) {
      const close = html.lastIndexOf('</article>');
      if (close > open) return html.slice(open, close + 10);
      return partial ? html.slice(open) : null;
    }
    at = open + 1;
  }
}

/** Every `<math ...>...</math>` replaced by its `alttext` (the TeX), so formulas read as TeX and not as glyphs. */
export function mathAsTex(html) {
  let out = '';
  let at = 0;
  for (;;) {
    const open = html.indexOf('<math', at);
    const next = open === -1 ? -1 : html.charCodeAt(open + 5);
    if (open === -1) return out + html.slice(at);
    if (next !== 32 && next !== 62 && next !== 10) {
      out += html.slice(at, open + 5);
      at = open + 5;
      continue;
    }
    const tagEnd = html.indexOf('>', open);
    const close = tagEnd === -1 ? -1 : html.indexOf('</math>', tagEnd);
    if (close === -1) return out + html.slice(at, open);
    const alt = attribute(html.slice(open, tagEnd + 1), 'alttext');
    out += html.slice(at, open) + (alt ? ` ${alt.replace(/[<>]/g, ' ')} ` : ' ');
    at = close + 7;
  }
}

//: A LaTeXML section heading's opening tag. No part of it may cross a `<` or `>`, so each attempt ends at the next tag
//: and the scan is linear (review of #428, gateway F1: `[^>]*` made it super-linear, 3.4 s on 52 KB of malformed
//: `<h2 ` openings, in the isolate that serves orders).
const HEADING = /<h([23])\s[^<>]*class="[^"<>]*ltx_title[^"<>]*"[^<>]*>/g;

/** `{ text, sections }` of an article: its readable text (at most MAX_TEXT_CHARS) and at most MAX_SECTIONS headings with
 * where each starts in the text, from at most MAX_HEADINGS headings looked at. */
export function articleText(article) {
  const html = mathAsTex(article);
  const text = cut(htmlToText(html).text, MAX_TEXT_CHARS);
  const sections = [];
  let cursor = 0;
  let seen = 0;
  HEADING.lastIndex = 0;
  for (let found = HEADING.exec(html); found && sections.length < MAX_SECTIONS && seen++ < MAX_HEADINGS; found = HEADING.exec(html)) {
    const close = html.indexOf(`</h${found[1]}>`, found.index);
    if (close === -1) break;
    const title = htmlToText(html.slice(found.index + found[0].length, close)).text.replace(/\s+/g, ' ').trim().slice(0, 120);
    HEADING.lastIndex = close;
    if (!title) continue;
    const start = text.indexOf(title, cursor);
    if (start === -1) continue;
    sections.push({ title, start });
    cursor = start + title.length;
  }
  return { text, sections };
}

// --- the upstream, paced -----------------------------------------------------------------------------------------------

const REDIRECTS = new Set([301, 302, 303, 307, 308]);
const inFlight = new Map();
let requestSeq = 0;
//: A request held longer than this no longer holds its place (a request the runtime ended never runs its `finally`):
//: past WORST_MS, as the web reader's (review of #428, gateway F7).
export const IN_FLIGHT_STALE_MS = 60_000;

/** Library requests this isolate serves now, stale places dropped. */
export function inFlightNow(at = Date.now()) {
  for (const [id, started] of inFlight) if (at - started > IN_FLIGHT_STALE_MS) inFlight.delete(id);
  return inFlight.size;
}

const defaultSleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/**
 * A turn for one request to `host`: `{ go: true, id }`, or `{ busy: true }` when the turn would come after the request's
 * deadline, or `{ cap }` when the day's upstream count is spent. Nothing is sent or counted unless it goes.
 */
async function acquire(host, ctx) {
  for (;;) {
    if (ctx.now() > ctx.deadline) return { busy: true, wait_ms: POLL_MS };  // no request starts past the budget
    const turn = await ctx.gate.libraryAcquire({ host, role: ctx.role });
    if (turn.go || turn.cap || turn.refused) return turn;
    const wait = Math.max(1, Number(turn.wait_ms) || POLL_MS);
    if (ctx.now() + wait > ctx.deadline) return { busy: true, wait_ms: wait };
    await ctx.sleep(Math.min(wait, POLL_MS));
  }
}

/** The API query `href` itself: the same host, path and query string (a redirect may not change the question). */
export const sameQuery = href => {
  const want = new URL(href);
  return url => url.hostname === API_HOST && url.pathname === want.pathname && url.search === want.search;
};

/** arxiv.org's HTML of exactly `<base>v<n>` (a trailing slash allowed). */
export const samePage = (base, n) => url => url.hostname === HTML_HOST
  && (url.pathname === `/html/${base}v${n}` || url.pathname === `/html/${base}v${n}/`);

/** ar5iv's rendering of `base`, unversioned or at a version no later than `latest` (the paper's confirmed latest). */
export const sameAr5iv = (base, latest) => url => {
  if (url.hostname !== AR5IV_HOST || !url.pathname.startsWith(`/html/${base}`)) return false;
  const rest = url.pathname.slice(`/html/${base}`.length).replace(/\/$/, '');
  if (rest === '') return true;
  const match = /^v([1-9][0-9]{0,2})$/.exec(rest);
  return Boolean(match) && Number(match[1]) <= latest;
};

/**
 * One upstream GET, paced: every hop (a redirect is another request) passes `checkLibraryUrl` and `expect` (the URL is
 * the item asked for: a redirect to another version, paper or query is refused, never fetched), waits its turn, and
 * releases its lease in a `finally`. `{ ok, status, text }` for a body of an accepted type; `{ status }` for any other
 * answer; `{ busy }`, `{ cap }` when it could not go; `{ failed }` when it went and nothing came back; `{ refused }`
 * for a URL outside the allowlist or not the item.
 */
async function fetchPaced(raw, ctx, { types, limit, expect }) {
  let current = raw;
  for (let hop = 0; ; hop++) {
    const checked = checkLibraryUrl(current);
    if (!checked.ok) return { refused: checked.error };
    if (typeof expect !== 'function' || !expect(checked.url)) return { refused: 'not the item asked for' };
    const turn = await acquire(checked.host, ctx);
    if (!turn.go) return turn;
    let status = 0;
    let retryMs = null;
    const signal = AbortSignal.timeout(FETCH_TIMEOUT_MS[checked.host]);
    try {
      const upstream = await ctx.fetcher(checked.url.href, {
        method: 'GET', headers: { 'User-Agent': USER_AGENT, Accept: types.join(', ') }, redirect: 'manual', signal,
      });
      status = upstream.status;
      const after = Number(upstream.headers.get('Retry-After'));
      retryMs = Number.isFinite(after) && after > 0 ? Math.min(after, 86400) * 1000 : null;
      if (REDIRECTS.has(status)) {
        const location = upstream.headers.get('Location');
        await discard(upstream);
        if (!location || hop >= MAX_REDIRECTS) return { status: 502, failed: 'a redirect the library does not follow' };
        try {
          current = new URL(location, checked.url).href;
        } catch {
          return { status: 502, failed: 'a redirect that cannot be parsed' };
        }
        continue;
      }
      const type = String(upstream.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
      if (!types.includes(type)) {
        await discard(upstream);
        return { status, type };
      }
      const body = await readCapped(upstream, limit, signal);
      return { ok: status >= 200 && status < 300, status, text: decode(body.bytes, upstream.headers.get('Content-Type')), cut: body.cut };
    } catch (error) {
      return { failed: signal.aborted || error?.name === 'TimeoutError' ? 'arXiv did not answer in time' : 'arXiv could not be reached' };
    } finally {
      await ctx.gate.libraryRelease({ id: turn.id, status, retry_after_ms: retryMs });
    }
  }
}

/** Entries from the API for `url`: `{ entries }`, or `{ response }` (the refusal to answer). */
async function apiEntries(url, ctx) {
  const got = await fetchPaced(url, ctx, { types: ['application/atom+xml', 'application/xml', 'text/xml'], limit: MAX_FEED_BYTES,
    expect: sameQuery(url) });
  if (got.busy) return { response: busy(got.wait_ms) };
  if (got.cap) return { response: json({ error: 'The library\'s upstream requests for today are spent.', cap: 'library_day' }, 429, { 'Retry-After': '3600' }) };
  if (got.refused) return { response: json({ error: `The library refused its own url: ${got.refused}.` }, 500) };
  if (got.failed) return { response: json({ error: `${got.failed}.`, upstream: true }, got.status === 502 ? 502 : 504) };
  if (BACKOFF_STATUSES.includes(got.status)) return { response: json({ error: `arXiv answered ${got.status}: the library backs off.`, upstream: true, backoff: true }, 503) };
  if (got.text === undefined) return { response: json({ error: `arXiv answered ${got.status} (${got.type || 'no type'}).`, upstream: true }, 502) };
  if (got.cut) return { response: json({ error: 'arXiv\'s feed was larger than the library reads.', upstream: true }, 502) };
  const feed = parseFeed(got.text);
  if (!feed.ok) return { response: json({ error: feed.error, upstream: true }, 502), api_error: feed.api_error };
  if (!got.ok) return { response: json({ error: `arXiv answered ${got.status}.`, upstream: true }, 502) };
  return { entries: feed.entries };
}

const busy = (waitMs = POLL_MS) => json({ error: 'The library is busy (arXiv is read one request at a time); ask again shortly.', busy: true },
  429, { 'Retry-After': String(Math.max(3, Math.ceil((Number(waitMs) || POLL_MS) / 1000))) });

// --- the cache ---------------------------------------------------------------------------------------------------------

async function kvGet(env, key) {
  if (!env.LIBRARY) return null;
  try {
    return await env.LIBRARY.get(key, 'json');
  } catch {
    return null;
  }
}

async function kvPut(env, key, value, ttl) {
  if (!env.LIBRARY) return;
  try {
    await env.LIBRARY.put(key, JSON.stringify(value), { expirationTtl: ttl });
  } catch {
    // A cache that cannot be written is a cache miss next time, never a failed answer.
  }
}

async function sha256(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}

const answer = (body, cache, status = 200) => json(body, status, { [CACHE_HEADER]: cache });
const refuse = (status, refused, error) => json({ error, refused }, status);

// --- a paper as it stood at the end of 2024 ----------------------------------------------------------------------------

const pinned = entry => ({ base: entry.base, version: entry.version, title: entry.title, summary: entry.summary, published: entry.published,
  updated: entry.updated, authors: entry.authors, categories: entry.categories, primary: entry.primary });

/** A cached pinned version that can be served as it is. */
const servable = (meta, base, n) => Boolean(meta) && meta.base === base && meta.version === n && judge(meta) === 'ok'
  && typeof meta.title === 'string' && typeof meta.summary === 'string' && Array.isArray(meta.authors) && Array.isArray(meta.categories);

/**
 * The newest version of a paper dated before the cutoff, from `versions` (version number -> entry), walking down from
 * version `n`: `{ entry }`; `{ missing: k }` when version k, which the walk needs, is not held; `{ refused }`
 * ('no_reliable_date', or 'after_cutoff' when even v1 is) when a version's dates cannot be relied on. The first version
 * that passes the rule is the one: every version above it is after the cutoff.
 */
export function newestBefore(versions, n) {
  for (let k = n; k >= 1; k--) {
    const entry = versions.get(k);
    if (!entry) return { missing: k };
    const verdict = judge(entry);
    if (verdict === 'ok') return { entry };
    if (verdict !== 'revised') return { refused: verdict };
  }
  return { refused: 'after_cutoff' };
}

/** The cached pinned metadata of version `n` of `base` when it can be served, else null. */
async function cachedMeta(env, base, n) {
  const meta = await kvGet(env, `m:${base}v${n}`);
  return servable(meta, base, n) ? meta : null;
}

/** The paper's newest version before the cutoff from the cache (`e:`, then its `m:`), or null. */
async function cachedBest(env, base) {
  const best = await kvGet(env, `e:${base}`);
  return best && Number.isInteger(best.version) && best.version >= 1 ? cachedMeta(env, base, best.version) : null;
}

/** Every version of `base` in `versions` that passes the rule kept as pinned metadata (`m:`), and `best`, the paper's
 * newest version before the cutoff, as `e:` (it never changes: every version posted from now on is after the cutoff). */
async function remember(env, base, versions, best) {
  const writes = [...versions.values()].filter(entry => typeof entry.title === 'string' && judge(entry) === 'ok')
    .map(entry => kvPut(env, `m:${base}v${entry.version}`, pinned(entry), TTL.meta));
  if (best) writes.push(kvPut(env, `e:${base}`, { version: best.version }, TTL.best));
  await Promise.all(writes);  // each write swallows its own failure (`kvPut`)
}

/** API entries grouped by paper: base -> (version -> pinned entry), for the papers in `bases` only. */
function byPaper(entries, bases) {
  const out = new Map();
  for (const entry of entries) {
    if (!entry.base || !entry.version || !bases.has(entry.base)) continue;
    if (!out.has(entry.base)) out.set(entry.base, new Map());
    out.get(entry.base).set(entry.version, pinned(entry));
  }
  return out;
}

// --- search ------------------------------------------------------------------------------------------------------------

//: What a search withheld, for the House's log only (it never reaches a model).
const WITHHELD = () => ({ after_cutoff: 0, revised_earlier: 0, revised_unmatched: 0, off_topic: 0, no_date: 0, unresolved: 0,
  too_many_versions: 0 });

async function search(url, env, ctx) {
  const maxRaw = url.searchParams.get('max');
  const max = maxRaw === null || maxRaw === '' ? 5 : Number(maxRaw);
  if (!Number.isInteger(max) || max < 1 || max > 10) return refuse(400, 'query', 'max must be a whole number from 1 to 10.');
  const built = buildQuery(url.searchParams.get('q'), url.searchParams.get('cat') || 'all');
  if (built.error) return refuse(400, 'query', built.error);
  // v: 2, the review's fixes: titles and abstracts only, every term in a revised paper's served version, and the newest
  // version before the cutoff served (answers cached under v: 1 are never read again).
  const key = `s:${await sha256(JSON.stringify({ v: 2, terms: built.terms, cat: built.cat, max }))}`;
  const head = { query: built.terms, category: built.cat, last_day: LAST_DAY };
  const cached = await kvGet(env, key);
  if (cached && Array.isArray(cached.items)) {
    const items = cached.items.map(admitItem).filter(Boolean);
    if (items.length === cached.items.length) return answer({ ...head, items, withheld: WITHHELD(), cached: true }, 'hit');
  }

  const found = await apiEntries(searchUrl(built.query, Math.min(2 * max, 20)), ctx);
  if (found.response) return found.response;
  const withheld = WITHHELD();
  const ranked = [];  // entries in arXiv's order: admitted as they are, or waiting for their newest version before the cutoff
  const revised = new Map();  // a paper revised after 2024 -> its latest version's number
  for (const entry of found.entries) {
    const verdict = judge(entry);
    if (verdict === 'ok') {
      ranked.push({ entry });
    } else if (verdict === 'revised') {
      ranked.push({ revised: entry.base });
      if (!revised.has(entry.base)) revised.set(entry.base, entry.version);
    } else {
      withheld[verdict === 'after_cutoff' ? 'after_cutoff' : 'no_date'] += 1;
    }
  }
  // Each revised paper is served as it stood at the end of 2024, as a read serves it: its newest version before the
  // cutoff, from the cache (`e:`) or from ONE batched call for the versions below every such paper's latest (matched by
  // id: the API answers in no fixed order).
  const chosen = new Map();  // base -> { entry } or { withheld: <why> }
  const ask = [];
  for (const [base, n] of revised) {
    const hit = await cachedBest(env, base);
    if (hit) chosen.set(base, { entry: hit });
    else if (n < 2) chosen.set(base, { withheld: 'no_date' });  // a v1 dated after its own posting: unreliable
    else if (n - 1 > MAX_VERSIONS || ask.length + n - 1 > MAX_BATCH_IDS) chosen.set(base, { withheld: 'too_many_versions' });
    else for (let k = 1; k < n; k++) ask.push(`${base}v${k}`);
  }
  let complete = true;
  if (ask.length) {
    const got = await apiEntries(idsUrl(ask), ctx);
    if (got.entries) {
      const papers = byPaper(got.entries, revised);
      for (const [base, n] of revised) {
        if (chosen.has(base)) continue;
        const versions = papers.get(base) || new Map();
        const walk = newestBefore(versions, n - 1);
        if (walk.missing) {
          chosen.set(base, { withheld: 'unresolved' });
          complete = false;  // arXiv left out a version that exists: ask again another time
          continue;
        }
        chosen.set(base, walk.entry ? { entry: walk.entry } : { withheld: walk.refused === 'after_cutoff' ? 'after_cutoff' : 'no_date' });
        await remember(env, base, versions, walk.entry);
      }
    } else {
      complete = false;  // busy, capped or failed: the revised papers are left out and the answer is not cached
    }
  }
  const items = [];
  for (const row of ranked) {
    let entry = row.entry;
    if (row.revised) {
      const pick = chosen.get(row.revised) || { withheld: 'unresolved' };
      if (!pick.entry) {
        withheld[pick.withheld] += 1;
        continue;
      }
      if (!matchesTerms(pick.entry, built.terms)) {
        withheld.revised_unmatched += 1;  // found only through words its own version lacks
        continue;
      }
      withheld.revised_earlier += 1;
      entry = pick.entry;
    }
    if (!onTopic(entry)) {
      withheld.off_topic += 1;
      continue;
    }
    const item = itemOf(entry);
    if (!item) {
      withheld.no_date += 1;
      continue;
    }
    if (!items.some(i => i.id === item.id)) items.push(item);
    if (items.length >= max) break;
  }
  if (complete) await kvPut(env, key, { items }, TTL.search);
  return answer({ ...head, items, withheld, cached: false }, 'miss');
}

// --- read --------------------------------------------------------------------------------------------------------------

const knownLatest = latest => Boolean(latest) && Number.isInteger(latest.version) && latest.version >= 1
  && stampMs(latest.updated) !== null && stampMs(latest.published) !== null;

/**
 * What a read needs of paper `parsed.base`: its latest version (`latest`: number, dates, when read), in `versions` the
 * version named (a read that names one), and in `best` the newest version before the cutoff (an unversioned read). From
 * the cache (`l:`, `m:`, `e:`) when it holds them, else from the API: ONE call (`id_list=<base>,<base>v<named, or 1>`,
 * matched by id), and for an unversioned read of a paper revised after 2024 with three or more versions, ONE more for
 * the versions between. `{ latest, versions, best, cached }` or `{ response }`.
 */
async function versionsOf(parsed, env, ctx) {
  const { base } = parsed;
  const latest = await kvGet(env, `l:${base}`);
  if (knownLatest(latest)) {
    const stub = { base, version: latest.version, published: latest.published, updated: latest.updated };
    const versions = new Map([[latest.version, stub]]);
    if (parsed.version) {
      // A version past the latest known does not exist, or was posted since (so after the cutoff): no such version.
      if (parsed.version > latest.version) return { latest, versions, cached: true };
      const meta = await cachedMeta(env, base, parsed.version);
      if (meta) return { latest, versions: versions.set(parsed.version, meta), cached: true };
      if (parsed.version === latest.version && judge(stub) === 'revised') return { latest, versions, cached: true };
      const best = await kvGet(env, `e:${base}`);
      if (best && Number.isInteger(best.version) && parsed.version > best.version) return { latest, versions, cached: true };
    } else {
      const best = judge(stub) === 'ok' ? await cachedMeta(env, base, latest.version) : await cachedBest(env, base);
      if (best) return { latest, versions: versions.set(best.version, best), best, cached: true };
    }
  }
  const got = await apiEntries(idsUrl([...new Set([base, `${base}v${parsed.version || 1}`])]), ctx);
  if (got.api_error) return { response: NO_PAPER(base) };
  if (got.response) return { response: got.response };
  const versions = byPaper(got.entries, new Set([base])).get(base) || new Map();
  if (!versions.size) return { response: NO_PAPER(base) };
  const top = versions.get(Math.max(...versions.keys()));
  const newest = { version: top.version, updated: top.updated, published: top.published, at: ctx.now() };
  await kvPut(env, `l:${base}`, newest, TTL.latest);
  let best = null;
  if (!parsed.version) {
    let walk = newestBefore(versions, top.version);
    if (walk.missing) {
      // Revised after 2024, with versions between v1 and the latest: ONE more call for them (the newest MAX_VERSIONS).
      const need = [];
      for (let k = Math.max(2, top.version - MAX_VERSIONS); k < top.version; k++) if (!versions.has(k)) need.push(`${base}v${k}`);
      const more = need.length ? await apiEntries(idsUrl(need), ctx) : { entries: [] };
      if (more.response) return { response: more.response };
      for (const [n, entry] of byPaper(more.entries, new Set([base])).get(base) || []) if (n < top.version) versions.set(n, entry);
      walk = newestBefore(versions, top.version);
    }
    best = walk.entry || null;
  }
  await remember(env, base, versions, best);
  return { latest: newest, versions, best, cached: false };
}

/** The paper's latest version read from arXiv now (ONE call, `id_list=<base>`), kept as `l:`; null when it cannot be. */
async function confirmLatest(base, env, ctx) {
  const got = await apiEntries(idsUrl([base]), ctx);
  const versions = got.entries ? byPaper(got.entries, new Set([base])).get(base) : null;
  if (!versions || !versions.size) return null;
  const top = versions.get(Math.max(...versions.keys()));
  const newest = { version: top.version, updated: top.updated, published: top.published, at: ctx.now() };
  await kvPut(env, `l:${base}`, newest, TTL.latest);
  return newest;
}

const AFTER = () => refuse(403, 'after_cutoff', 'The library holds research posted before its cutoff only.');
const UNRELIABLE = () => refuse(403, 'no_reliable_date', 'That item\'s dates cannot be relied on.');
const NO_PAPER = base => refuse(404, 'not_found', `arXiv has no paper ${base}.`);
//: A version that does not exist and a version dated after the cutoff get this same answer (review of #428, look-ahead F3).
const NO_VERSION = parsed => refuse(404, 'not_found', `arXiv has no version ${parsed.version} of ${parsed.base}.`);

/**
 * The version a read serves: a named version only as itself and only when it passes the rule (one after the cutoff is
 * `NO_VERSION`, exactly as one that does not exist); an unversioned read, the paper's newest version before the cutoff
 * (`instead`: a later version exists, for the House's log only). `{ entry, instead }` or `{ response }`.
 */
function choose(parsed, found) {
  const n = found.latest.version;
  if (parsed.version) {
    const entry = found.versions.get(parsed.version);
    const verdict = entry ? judge(entry) : 'missing';
    if (verdict === 'ok') return { entry, instead: false };
    if (verdict === 'no_reliable_date') return { response: UNRELIABLE() };
    if (verdict === 'after_cutoff') return { response: AFTER() };
    return { response: NO_VERSION(parsed) };
  }
  const walk = found.best ? { entry: found.best } : newestBefore(found.versions, n);
  if (walk.entry) return { entry: walk.entry, instead: walk.entry.version !== n };
  return { response: walk.refused === 'after_cutoff' ? AFTER() : UNRELIABLE() };
}

/**
 * Text as it may be served, email addresses redacted: arXiv's own HTML (pinned) with every post-cutoff date as "[date]";
 * ar5iv's (not pinned) whole, or null when it names any post-cutoff date. The sections are found again in the text served.
 */
export function servedText(source, text, sections) {
  if (typeof text !== 'string' || !Array.isArray(sections)) return null;
  let clean;
  if (source === 'ar5iv') {
    if (hasPostCutoff(text) || sections.some(s => hasPostCutoff(String(s?.title)))) return null;
    clean = redactEmails(text);
  } else if (source === 'arxiv_html') {
    clean = scrubDates(redactEmails(text));
    if (clean === null) return null;
  } else {
    return null;
  }
  const found = [];
  let cursor = 0;
  for (const section of sections.slice(0, MAX_SECTIONS)) {
    const title = source === 'ar5iv' ? String(section?.title || '') : scrubDates(String(section?.title || ''));
    const start = title ? clean.indexOf(title, cursor) : -1;
    if (start === -1) continue;
    found.push({ title, start });
    cursor = start + title.length;
  }
  return { text: clean, sections: found };
}

const BUSY_NOTE = 'the full text was not fetched now (the library is busy); ask again later';
const FAILED_NOTE = 'the full text could not be read now; ask again later';

/** True when a fetch's outcome is lasting: the page is there (2xx) or is not (404, 410). A fetch that did not go, did
 * not come back, was refused, or met another answer (a 403 or 451 is how a blocked address is told: review of #428,
 * gateway F3) says nothing lasting, so "no text" is not remembered for it. */
const settled = got => got.status === 404 || got.status === 410 || (got.status >= 200 && got.status < 300);

/**
 * `{ source, text, sections }` of the pinned version `entry`, or `{ source: 'none', note }`. arXiv's own HTML first (a
 * version dated from HTML_SINCE_MS on; a page cut at MAX_PAGE_BYTES is read to its cut, as it is pinned), then ar5iv
 * only when `entry` is the paper's latest version and that latest is before the cutoff, confirmed within
 * LATEST_FRESH_MS (a whole page only: ar5iv is not pinned, so its every word is scanned). "No text" is remembered
 * (`t0:`) only when it is certain.
 */
async function textOf(entry, found, env, ctx) {
  const key = `${entry.base}v${entry.version}`;
  const stored = await kvGet(env, `t:${key}`);
  if (stored) {
    const served = servedText(stored.source, stored.text, stored.sections);
    if (served) return { source: stored.source, ...served, cached: true };
  }
  if (await kvGet(env, `t0:${key}`)) return { source: 'none', cached: true };
  const types = ['text/html', 'application/xhtml+xml'];
  let certain = true;
  let note = null;
  if (stampMs(entry.updated) >= HTML_SINCE_MS) {
    const got = await fetchPaced(`https://${HTML_HOST}/html/${key}`, ctx, { types, limit: MAX_PAGE_BYTES,
      expect: samePage(entry.base, entry.version) });
    // A page over MAX_PAGE_BYTES is read to where it was cut and kept (review of #428, gateway F5: it was fetched again,
    // 3 MB and a 15 s turn, on every read, for no text).
    const article = got.ok ? articleOf(got.text, { partial: Boolean(got.cut) }) : null;
    if (article) {
      const raw = articleText(article);
      const served = servedText('arxiv_html', raw.text, raw.sections);
      if (served) {
        await kvPut(env, `t:${key}`, { source: 'arxiv_html', ...raw }, TTL.text);
        return { source: 'arxiv_html', ...served };
      }
    } else if (!settled(got)) {
      certain = false;
      note = got.busy || got.cap ? BUSY_NOTE : FAILED_NOTE;
    }
  }
  let latest = found.latest;
  if (entry.version === latest.version && stampMs(latest.updated) < CUTOFF_MS && ctx.now() - Number(latest.at) >= LATEST_FRESH_MS) {
    // ar5iv renders SOME version of the paper: the latest is confirmed first (a newer one after the cutoff ends ar5iv).
    latest = await confirmLatest(entry.base, env, ctx);
    if (!latest) {
      certain = false;
      note = note || BUSY_NOTE;
    }
  }
  if (latest && entry.version === latest.version && stampMs(latest.updated) < CUTOFF_MS) {
    const got = await fetchPaced(`https://${AR5IV_HOST}/html/${entry.base}`, ctx, { types, limit: MAX_PAGE_BYTES,
      expect: sameAr5iv(entry.base, latest.version) });
    const article = got.ok && !got.cut ? articleOf(got.text) : null;
    if (article) {
      const raw = articleText(article);
      const served = servedText('ar5iv', raw.text, raw.sections);
      if (served) {
        await kvPut(env, `t:${key}`, { source: 'ar5iv', ...raw }, TTL.text);
        return { source: 'ar5iv', ...served };
      }
    } else if (!settled(got)) {
      certain = false;
      note = note || (got.busy || got.cap ? BUSY_NOTE : FAILED_NOTE);
    }
  }
  if (certain) await kvPut(env, `t0:${key}`, { at: ctx.now() }, TTL.none);
  return { source: 'none', note };
}

const windowOf = (url, name, fallback, max) => {
  const raw = url.searchParams.get(name);
  if (raw === null || raw === '') return fallback;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 0 && value <= max ? value : null;
};

async function read(url, env, ctx) {
  const parsed = parseId(url.searchParams.get('id'));
  if (!parsed) return refuse(400, 'id', 'id must be an arXiv id such as arXiv:1602.00865v1.');
  if (idAfterCutoff(parsed)) return AFTER();
  const start = windowOf(url, 'start', 0, MAX_TEXT_CHARS);
  const chars = windowOf(url, 'chars', READ_CHARS, MAX_READ_CHARS);
  if (start === null || !chars) return refuse(400, 'id', `start must be 0 to ${MAX_TEXT_CHARS} and chars 1 to ${MAX_READ_CHARS}.`);
  const found = await versionsOf(parsed, env, ctx);
  if (found.response) return found.response;
  const chosen = choose(parsed, found);
  if (chosen.response) return chosen.response;
  const entry = chosen.entry;
  if (!onTopic(entry)) return refuse(403, 'off_topic', 'The library holds quantitative finance, econometrics, statistics and machine learning on markets.');
  const item = itemOf(entry);
  if (!item) return UNRELIABLE();
  const text = await textOf(entry, found, env, ctx);
  const full = text.text || '';
  const window = cut(full.slice(start), chars);
  const body = {
    ...item, asked: parsed.version ? `arXiv:${parsed.base}v${parsed.version}` : `arXiv:${parsed.base}`,
    served_earlier_version: chosen.instead, text_source: text.source, sections: (text.sections || []).slice(0, MAX_SECTIONS), start,
    text: window, next_start: start + window.length < full.length ? start + window.length : null, total_chars: full.length,
    last_day: LAST_DAY, cached: Boolean(found.cached && text.cached), ...(text.note ? { text_note: text.note } : {}),
  };
  if (hasPostCutoff(JSON.stringify(body))) return refuse(403, 'no_reliable_date', 'That item failed the library\'s date check.');
  return answer(body, body.cached ? 'hit' : 'miss');
}

// --- the routes --------------------------------------------------------------------------------------------------------

/** True for a path the library serves. */
export const isLibraryPath = path => Object.values(PATHS).includes(path);

/**
 * `GET /v1/research/*`. The caller has already been authenticated. `sleep` and `now` are the tests' (a fake clock);
 * `gate` is the Durable Object stub or, in tests, the gate itself.
 */
export async function libraryRoute(request, env, { gate, fetcher = fetch, now = Date.now, sleep = defaultSleep } = {}) {
  if (request.method !== 'GET') return json({ error: 'Method not allowed.' }, 405, { Allow: 'GET' });
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '');
  if (path === PATHS.health) {
    try {
      return json({ library: await gate.libraryStatus() });
    } catch {
      return json({ library: { error: 'library status unreadable' } }, 503);
    }
  }
  if (inFlightNow() >= MAX_IN_FLIGHT) return busy(5000);
  const role = url.searchParams.get('role');
  const ctx = { gate, fetcher, now, sleep, deadline: now() + REQUEST_BUDGET_MS, role: /^[a-z0-9][a-z0-9_-]{0,31}$/.test(role || '') ? role : null };
  const id = ++requestSeq;
  inFlight.set(id, Date.now());
  try {
    return path === PATHS.search ? await search(url, env, ctx) : await read(url, env, ctx);
  } catch (error) {
    // A library fault is this request's answer and nothing more: never an unhandled error in the isolate that serves orders.
    return json({ error: `The library failed (${String(error?.name || 'Error').slice(0, 40)}).` }, 500);
  } finally {
    inFlight.delete(id);
  }
}
