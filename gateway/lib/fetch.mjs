// The research web reader (Sept 25, 2026): `POST /v1/web/fetch {"url", "agent"}` reads ONE public
// http(s) page for a research agent and answers its readable text.
//
// Why here: the House box's egress is exact-host (it holds the Sail key and this gateway's token,
// and Sail's allowlist ignores wildcards), so the open web is read by this Worker instead. The
// strategy boxes stay sealed: this is a research tool, called by the House on an agent's behalf.
//
// What it will not do:
//   - send anything but a GET with a fixed, honest User-Agent and an Accept header: no cookies, no
//     Authorization, no credential of any kind, and never a header the caller sent;
//   - read a URL that is not http or https, names a port other than the scheme's default, carries
//     a user or password, is longer than MAX_URL_CHARS, or names a private, loopback, link-local,
//     CGNAT, multicast, unspecified, IPv4-mapped, unique-local or other non-public address, a
//     local or internal name, or this Worker's own domain -- checked on the request AND on every
//     redirect hop (redirects are followed by hand, at most MAX_REDIRECTS);
//   - read longer than TIMEOUT_MS, more than MAX_BODY_BYTES of body, or a content type outside
//     `readable` (the refusal names the type);
//   - answer more than MAX_TEXT_CHARS of text, or more than DAY_CAP pages a UTC day across the
//     floor (counted in the Gate, reported in /v1/health);
//   - read more than MAX_IN_FLIGHT pages at once in one isolate (the isolate that serves the
//     order routes), or spend more than linear time on a page's HTML.
//
// The kill switch does not stop it: it moves no money. A page that answers non-2xx is an answer,
// with its status, not an error. Names are not resolved here: a public name that resolves to a
// private address is left to Cloudflare's egress, which has no route to private networks.

import { json, fail, readBody, iso } from './http.mjs';

export const PATH = '/v1/web/fetch';
//: Pages a UTC day, the whole floor together (the House's own budget is 20 per agent a day).
export const DAY_CAP = 3000;
export const USER_AGENT = 'LTCM-research/1.0 (+https://blakewoods.us/capital)';
export const ACCEPT = 'text/html, application/xhtml+xml, application/json, text/plain, '
  + 'application/xml;q=0.9, application/rss+xml;q=0.9, application/atom+xml;q=0.9, text/*;q=0.8';
export const MAX_URL_CHARS = 2048;
export const MAX_REDIRECTS = 5;
export const TIMEOUT_MS = 15_000;
export const MAX_BODY_BYTES = 2 * 1024 * 1024;
export const MAX_TEXT_CHARS = 200_000;
//: The request body: a URL and an agent name.
const MAX_REQUEST_BYTES = 8 * 1024;
//: Beyond `text/*`, the application types it reads.
export const TYPES = ['application/json', 'application/xml', 'application/rss+xml', 'application/atom+xml', 'application/xhtml+xml'];
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
//: Pages read at once by one isolate. A page's body is held and turned into text in the same isolate
//: (128 MB, one thread) that serves the order routes, so a burst of research reads is refused, free
//: and uncounted, rather than crowding them out.
export const MAX_IN_FLIGHT = 4;
//: A read held longer than this no longer holds its place: a request the runtime terminated (its CPU
//: limit) never runs its `finally`, and four of them must not close the route for the isolate's life.
const IN_FLIGHT_STALE_MS = 60_000;
const inFlight = new Map();
let readSeq = 0;
/** Pages this isolate is reading now, stale places dropped. */
export function inFlightNow(at = Date.now()) {
  for (const [id, started] of inFlight) if (at - started > IN_FLIGHT_STALE_MS) inFlight.delete(id);
  return inFlight.size;
}
const AGENT = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const BLOCKED_NAMES = new Set(['localhost', 'metadata.google.internal']);
const BLOCKED_SUFFIXES = ['.localhost', '.local', '.internal', '.home.arpa', '.localdomain'];

// --- the URL rules ------------------------------------------------------------------------------

/** Four octets for a dotted-quad host, or null. The URL parser already turned `2130706433`, `0x7f.1`
 * and `127.1` into dotted quads, so this is the only IPv4 spelling left to check. */
function ipv4(host) {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!match) return null;
  const octets = match.slice(1).map(Number);
  return octets.every(n => n <= 255) ? octets : null;
}

/** Why an IPv4 address is not a public one, or null when it is. */
function privateV4([a, b, c, d]) {
  if (a === 169 && b === 254 && c === 169 && d === 254) return 'the metadata address';
  if (a === 0) return 'an unspecified address';
  if (a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)) return 'a private address';
  if (a === 127) return 'a loopback address';
  if (a === 169 && b === 254) return 'a link-local address';
  if (a === 100 && b >= 64 && b <= 127) return 'a shared (CGNAT) address';
  if (a >= 224 && a <= 239) return 'a multicast address';
  if (a >= 240) return 'a reserved address';
  if ((a === 192 && b === 0 && (c === 0 || c === 2)) || (a === 198 && b === 51 && c === 100)
      || (a === 203 && b === 0 && c === 113) || (a === 198 && (b === 18 || b === 19)) || (a === 192 && b === 88 && c === 99)) {
    return 'a reserved address';
  }
  return null;
}

/** Eight 16-bit groups for an IPv6 address (brackets already removed), or null. */
function ipv6(text) {
  let body = text.toLowerCase();
  const dotted = /(\d{1,3}(?:\.\d{1,3}){3})$/.exec(body);
  if (dotted) {
    const octets = ipv4(dotted[1]);
    if (!octets) return null;
    body = body.slice(0, -dotted[1].length)
      + `${((octets[0] << 8) | octets[1]).toString(16)}:${((octets[2] << 8) | octets[3]).toString(16)}`;
  }
  const halves = body.split('::');
  if (halves.length > 2) return null;
  const groups = part => (part ? part.split(':').map(h => (/^[0-9a-f]{1,4}$/.test(h) ? parseInt(h, 16) : NaN)) : []);
  const head = groups(halves[0]);
  const tail = halves.length === 2 ? groups(halves[1]) : [];
  if ([...head, ...tail].some(Number.isNaN)) return null;
  const fill = halves.length === 2 ? 8 - head.length - tail.length : 0;
  if (fill < 0 || (halves.length === 1 && head.length !== 8) || (halves.length === 2 && fill < 1)) return null;
  return [...head, ...Array(fill).fill(0), ...tail];
}

/** Why an IPv6 address is not a public one, or null. Only global unicast (2000::/3) is public, and
 * not the parts of it that embed an IPv4 address or are for documentation. */
function privateV6(g) {
  const zeros = n => g.slice(0, n).every(x => x === 0);
  if (g.every(x => x === 0)) return 'an unspecified address';
  if (zeros(7) && g[7] === 1) return 'a loopback address';
  if (zeros(5) && g[5] === 0xffff) return 'an IPv4-mapped address';
  if ((g[0] & 0xfe00) === 0xfc00) return 'a unique-local (ULA) address';
  if ((g[0] & 0xffc0) === 0xfe80) return 'a link-local address';
  if ((g[0] & 0xff00) === 0xff00) return 'a multicast address';
  if ((g[0] & 0xe000) !== 0x2000) return 'a non-global address';
  if (g[0] === 0x2001 && (g[1] === 0 || g[1] === 0x0db8)) return 'a reserved address';  // Teredo, documentation
  if (g[0] === 0x2002) return 'a reserved address';  // 6to4 embeds an IPv4 address
  return null;
}

/** The domains a URL may not name: this Worker's own host and, on workers.dev, its account's subdomain. */
export function ownDomains(host) {
  const name = String(host || '').toLowerCase().replace(/\.+$/, '');
  if (!name) return [];
  const labels = name.split('.');
  return name.endsWith('.workers.dev') && labels.length > 3 ? [name, labels.slice(-3).join('.')] : [name];
}

/**
 * The URL rules. Answers `{ url }` (a parsed URL, fragment dropped) or `{ error }` naming the rule.
 * Checked on the request and again on every redirect's target.
 */
export function checkUrl(raw, own = []) {
  if (typeof raw !== 'string' || !raw.trim()) return { error: 'A url is required.' };
  if (raw.length > MAX_URL_CHARS) return { error: `The url is longer than ${MAX_URL_CHARS} characters.` };
  let url;
  try {
    url = new URL(raw.trim());
  } catch {
    return { error: 'The url cannot be parsed.' };
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return { error: `Only http and https are read, not ${url.protocol.replace(/:$/, '')}.` };
  if (url.username || url.password) return { error: 'A url with a user or password is refused.' };
  // The parser empties `port` when it is the scheme's default (80 for http, 443 for https).
  if (url.port !== '') return { error: `Only the default port is read, not ${url.port}.` };
  url.hash = '';
  if (url.href.length > MAX_URL_CHARS) return { error: `The url is longer than ${MAX_URL_CHARS} characters.` };
  const host = url.hostname.toLowerCase().replace(/\.+$/, '');
  if (!host) return { error: 'The url names no host.' };
  if (host.startsWith('[')) {
    const groups = ipv6(host.slice(1, -1));
    if (!groups) return { error: 'The url names an address that cannot be read.' };
    const why = privateV6(groups);
    return why ? { error: `The url names ${why}.` } : { url };
  }
  const octets = ipv4(host);
  if (octets) {
    const why = privateV4(octets);
    return why ? { error: `The url names ${why}.` } : { url };
  }
  if (BLOCKED_NAMES.has(host) || BLOCKED_SUFFIXES.some(suffix => host.endsWith(suffix))) {
    return { error: `The url names a local or internal host (${host}).` };
  }
  if (!host.includes('.')) return { error: `The url names a host with no domain (${host}).` };
  if (own.some(domain => host === domain || host.endsWith('.' + domain))) {
    return { error: 'The url names the gateway\'s own domain.' };
  }
  return { url };
}

// --- what a page is turned into -----------------------------------------------------------------

//: A media type as RFC 9110 spells one (`type/subtype`, token characters), bounded: the header is the
//: page's to write, and what is answered and recorded must not be a page's worth of text.
const MEDIA_TYPE = /^[a-z0-9][a-z0-9!#$&^_.+-]{0,62}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,62}$/;

/** The media type of a Content-Type header, lower case, parameters dropped; '' when there is none
 * or it is not a well-formed media type. */
export function mediaType(header) {
  const type = String(header || '').split(';')[0].trim().toLowerCase();
  return MEDIA_TYPE.test(type) ? type : '';
}

export const readable = type => type.startsWith('text/') || TYPES.includes(type);
const isHtml = type => type === 'text/html' || type === 'application/xhtml+xml';

const NAMED = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', ndash: '–', mdash: '—', hellip: '…',
  lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”', laquo: '«', raquo: '»', bull: '•', middot: '·',
  copy: '©', reg: '®', trade: '™', deg: '°', plusmn: '±', times: '×', divide: '÷', minus: '−',
  frac12: '½', frac14: '¼', frac34: '¾', cent: '¢', pound: '£', euro: '€', yen: '¥', sect: '§',
  para: '¶', shy: '', zwj: '', zwnj: '', thinsp: ' ', ensp: ' ', emsp: ' ', larr: '←', rarr: '→',
  uarr: '↑', darr: '↓', le: '≤', ge: '≥', ne: '≠', asymp: '≈', infin: '∞', micro: 'µ', prime: '′',
};

/** Character references decoded: the named ones above, and every numeric one. */
export function decodeEntities(text) {
  return text.replace(/&(#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});/g, (whole, ref) => {
    if (ref[0] !== '#') return Object.hasOwn(NAMED, ref) ? NAMED[ref] : whole;
    const code = ref[1] === 'x' || ref[1] === 'X' ? parseInt(ref.slice(2), 16) : parseInt(ref.slice(1), 10);
    return code > 0 && code <= 0x10ffff && (code < 0xd800 || code > 0xdfff) ? String.fromCodePoint(code) : '\uFFFD';
  });
}

// The page is read in ONE forward pass, never with a pattern that can scan past a tag it could not
// close: a regex like `<[a-z](?:"[^"]*"|[^">])*>` retried at every `<` of a page with no `>` is
// super-linear: 32 KB of `<a<a<a...` took 22 seconds on a (loaded) test machine, the cost growing
// faster than the square of the page, and the isolate -- with every order request on it -- waits
// for it. A tag that never closes, or a dropped element that never ends, ends the text there, as it
// would in a browser.

//: Never text. The title is answered on its own, so it is not repeated in the text.
const DROPPED = new Set(['script', 'style', 'noscript', 'svg', 'template', 'title']);
const BLOCK_TAGS = new Set(['p', 'div', 'section', 'article', 'header', 'footer', 'main', 'nav', 'aside', 'h1', 'h2', 'h3', 'h4',
  'h5', 'h6', 'ul', 'ol', 'dl', 'dt', 'dd', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'pre', 'blockquote', 'figure', 'figcaption',
  'form', 'fieldset', 'address', 'details', 'summary', 'caption', 'br', 'hr']);
const CELL_TAGS = new Set(['td', 'th']);
//: What a head holds. Any other element ends it, as a browser's parser would: its close is optional.
const IN_HEAD = new Set(['html', 'head', 'title', 'meta', 'link', 'style', 'script', 'noscript', 'base', 'template']);
//: The raw characters of a title considered: a title is shown to 300 characters.
const MAX_TITLE_SOURCE = 4096;
const CLOSES = new Map([...DROPPED].map(name => [name, new RegExp(`</${name}\\s*>`, 'gi')]));
//: No name acted on is longer than this ('blockquote', 'figcaption'): a longer one is any other tag.
const MAX_NAME = 10;

const isSpaceCode = code => code === 32 || code === 9 || code === 10 || code === 13 || code === 12;
const isLetterCode = code => (code >= 65 && code <= 90) || (code >= 97 && code <= 122);
const isNameCode = code => isLetterCode(code) || (code >= 48 && code <= 58) || code === 45;

/** Just past the `>` that closes the tag opening at `at` (a quoted value may hold `>`), or -1. */
function tagEnd(html, at) {
  const n = html.length;
  for (let k = at + 1; k < n; k++) {
    const code = html.charCodeAt(k);
    if (code === 62) return k + 1;
    if (code === 34 || code === 39) {
      const quoteEnd = html.indexOf(code === 34 ? '"' : "'", k + 1);
      if (quoteEnd === -1) return -1;
      k = quoteEnd;
    }
  }
  return -1;
}

/** The lower-case name of the element whose tag opens at `at`; '*' for one whose name is longer than
 * any acted on; '' for a doctype, `<?...>` or a malformed name. */
function tagName(html, at, closing) {
  const start = at + (closing ? 2 : 1);
  if (!isLetterCode(html.charCodeAt(start))) return '';
  let k = start + 1;
  while (k - start <= MAX_NAME && isNameCode(html.charCodeAt(k))) k++;
  if (k - start > MAX_NAME) return '*';
  const after = html.charCodeAt(k);
  return after === 47 || after === 62 || isSpaceCode(after) ? html.slice(start, k).toLowerCase() : '';
}

/** The page's text, in one forward pass, and its first title's raw source (or null). */
function readText(html, { titles = true } = {}) {
  const starts = /<[a-zA-Z/!?]/g;  // `<` then anything else is text
  let text = '';
  let title = null;
  let head = 'before';  // 'before' the head, 'in' it (its text dropped), or 'after' it
  const n = html.length;
  let i = 0;
  for (;;) {
    starts.lastIndex = i;
    const found = starts.exec(html);
    const lt = found ? found.index : n;
    if (head !== 'in' && lt > i) text += html.slice(i, lt);
    if (!found) break;
    if (html.startsWith('<!--', lt)) {
      const end = html.indexOf('-->', lt + 4);
      if (end === -1) break;
      if (head !== 'in') text += ' ';
      i = end + 3;
      continue;
    }
    const end = tagEnd(html, lt);
    if (end === -1) break;
    i = end;
    const closing = html.charCodeAt(lt + 1) === 47;
    const name = tagName(html, lt, closing);
    if (!name) continue;
    if (head === 'before' && !closing && name === 'head') {
      head = 'in';
      continue;
    }
    if (head === 'in' && (closing ? name === 'head' : !IN_HEAD.has(name))) {
      head = 'after';
      if (closing) continue;
    }
    if (!closing && DROPPED.has(name)) {
      if (name === 'svg' && html.charCodeAt(end - 2) === 47) continue;  // <svg ... /> holds nothing
      const close = CLOSES.get(name);
      close.lastIndex = end;
      const shut = close.exec(html);
      if (titles && name === 'title' && title === null && shut) title = html.slice(end, Math.min(shut.index, end + MAX_TITLE_SOURCE));
      if (!shut) break;
      if (head !== 'in') text += ' ';
      i = shut.index + shut[0].length;
      continue;
    }
    if (head === 'in') continue;
    if (!closing && name === 'li') text += '\n- ';
    else if (!closing && CELL_TAGS.has(name)) text += ' | ';
    else if (BLOCK_TAGS.has(name)) text += '\n';
  }
  return { text, title };
}

/** Readable text from an HTML page: its title, and its body without scripts, styles, `noscript`,
 * `svg`, `template` or the head, links kept as their text, whitespace collapsed. Linear in the page. */
export function htmlToText(html) {
  const { text, title } = readText(html);
  const heading = title === null ? '' : collapse(decodeEntities(readText(title, { titles: false }).text)).replace(/\s+/g, ' ').slice(0, 300);
  return { title: heading, text: collapse(decodeEntities(text)) };
}

/** Spaces collapsed within lines, lines trimmed, a table row's leading `|` dropped, at most one
 * blank line in a row. Global replaces only: a page of empty lines is not a million calls. */
function collapse(text) {
  return text
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t\f\v  -​　]+/g, ' ')
    .replace(/ ?\n ?/g, '\n')
    .replace(/(^|\n)\| ?/g, '$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/** At most `limit` UTF-16 units, never ending in half a surrogate pair. */
function cut(text, limit) {
  if (text.length <= limit) return text;
  const code = text.charCodeAt(limit - 1);
  return text.slice(0, code >= 0xd800 && code <= 0xdbff ? limit - 1 : limit);
}

function decode(bytes, header) {
  const charset = /;\s*charset\s*=\s*"?([^";\s]+)/i.exec(String(header || ''))?.[1];
  try {
    return new TextDecoder(charset || 'utf-8').decode(bytes);
  } catch {
    return new TextDecoder('utf-8').decode(bytes);
  }
}

/** The body, at most `limit` bytes: `{ bytes, size, cut }`. Reading stops at the limit or the deadline. */
async function readCapped(response, limit, signal) {
  if (!response.body) return { bytes: new Uint8Array(0), size: 0, cut: false };
  const reader = response.body.getReader();
  const aborted = new Promise((_, reject) => {
    if (signal.aborted) reject(signal.reason);
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
  aborted.catch(() => {});
  const chunks = [];
  let size = 0;
  let over = false;
  try {
    for (;;) {
      const { done, value } = await Promise.race([reader.read(), aborted]);
      if (done) break;
      if (size + value.byteLength > limit) {
        chunks.push(value.subarray(0, limit - size));
        size = limit;
        over = true;
        break;
      }
      chunks.push(value);
      size += value.byteLength;
    }
  } finally {
    if (over || signal.aborted) await reader.cancel().catch(() => {});
  }
  const bytes = new Uint8Array(size);
  let at = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, at);
    at += chunk.byteLength;
  }
  return { bytes, size, cut: over };
}

const discard = response => response.body?.cancel().catch(() => {});

// --- the route ----------------------------------------------------------------------------------

/** The only headers that ever leave with a fetch. */
export const outgoingHeaders = () => ({ 'User-Agent': USER_AGENT, Accept: ACCEPT, 'Accept-Language': 'en' });

/**
 * `POST /v1/web/fetch`. Every answer after the URL is read names it (`url`), so the House can tell
 * a judged page from a gateway that could not act (a bad body, the day's cap).
 */
export async function webFetch(request, env, { gate, fetcher = fetch, now = Date.now, timeoutMs = TIMEOUT_MS } = {}) {
  const body = await readBody(request, MAX_REQUEST_BYTES);
  if (body.error) return fail(body.error, 413);
  let asked;
  try {
    asked = JSON.parse(body.text || '');
  } catch {
    return fail('The request must be JSON: {"url": "...", "agent": "..."}.', 400);
  }
  if (!asked || typeof asked !== 'object' || Array.isArray(asked) || typeof asked.url !== 'string' || !asked.url.trim()) {
    return fail('The request needs a url.', 400);
  }
  const shown = asked.url.trim().slice(0, 300);
  const own = ownDomains(new URL(request.url).hostname);
  const first = checkUrl(asked.url, own);
  if (first.error) return json({ error: first.error, url: shown, refused: 'url' }, 403);
  const agent = typeof asked.agent === 'string' && AGENT.test(asked.agent) ? asked.agent : null;
  if (inFlightNow() >= MAX_IN_FLIGHT) {
    return json({ error: `The gateway is already reading ${MAX_IN_FLIGHT} pages; ask again in a few seconds.`, busy: true },
      429, { 'Retry-After': '5' });
  }
  const id = ++readSeq;
  inFlight.set(id, Date.now());
  try {
    return await readPage(first.url, own, { gate, agent, fetcher, now, timeoutMs });
  } finally {
    inFlight.delete(id);
  }
}

/** The day's place, then the page: every answer from here names the url. */
async function readPage(first, own, { gate, agent, fetcher, now, timeoutMs }) {
  const place = await gate.webFetchReserve({ at: now(), agent });
  if (!place.ok) return json({ error: place.error, cap: place.cap }, place.status, { 'Retry-After': '3600' });

  const url = first.href;
  const signal = AbortSignal.timeout(timeoutMs);
  let current = first;
  let upstream;
  try {
    for (let redirects = 0; ; redirects++) {
      upstream = await fetcher(current.href, { method: 'GET', headers: outgoingHeaders(), redirect: 'manual', signal });
      const location = REDIRECT_STATUSES.has(upstream.status) ? upstream.headers.get('Location') : null;
      if (!location) break;
      await discard(upstream);
      if (redirects >= MAX_REDIRECTS) {
        return json({ error: `The page redirected more than ${MAX_REDIRECTS} times.`, url, final_url: current.href }, 502);
      }
      let next;
      try {
        next = new URL(location, current);
      } catch {
        return json({ error: 'The page redirected to a url that cannot be parsed.', url, final_url: current.href }, 502);
      }
      const hop = checkUrl(next.href, own);
      if (hop.error) {
        return json({ error: `The redirect to ${next.href.slice(0, 300)} is refused: ${hop.error}`, url, final_url: current.href, refused: 'redirect' }, 403);
      }
      current = hop.url;
    }
    const header = upstream.headers.get('Content-Type');
    const type = mediaType(header);
    if (!readable(type)) {
      await discard(upstream);
      return json({ error: `The page's content type ${type || (header ? '(malformed)' : '(none)')} is not one the gateway reads.`, url,
        final_url: current.href, status: upstream.status, content_type: type || null }, 415);
    }
    const raw = await readCapped(upstream, MAX_BODY_BYTES, signal);
    const decoded = decode(raw.bytes, upstream.headers.get('Content-Type'));
    const page = isHtml(type) ? htmlToText(decoded) : { title: '', text: decoded.trim() };
    const text = cut(page.text, MAX_TEXT_CHARS);
    return json({
      url, final_url: current.href, status: upstream.status, content_type: type, title: page.title, text,
      truncated: raw.cut || text.length < page.text.length, bytes: raw.size, fetched_at: iso(now()),
    });
  } catch (error) {
    if (signal.aborted || error?.name === 'TimeoutError' || error?.name === 'AbortError') {
      return json({ error: `The page did not answer within ${Math.round(timeoutMs / 1000)} seconds.`, url, final_url: current.href }, 504);
    }
    return json({ error: `The page could not be read: ${error?.name || 'fetch failed'}.`, url, final_url: current.href }, 502);
  }
}
