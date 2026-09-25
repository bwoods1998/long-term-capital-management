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
//     floor (counted in the Gate, reported in /v1/health).
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

/** The media type of a Content-Type header, lower case, parameters dropped; '' when none. */
export function mediaType(header) {
  return String(header || '').split(';')[0].trim().toLowerCase();
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

// A tag with its attributes, quoted values allowed to hold `>`.
const ATTRS = `(?:"[^"]*"|'[^']*'|[^'">])*`;
const tag = (names, { close = true } = {}) => new RegExp(`<${close ? '\\/?' : ''}(?:${names})(?=[\\s/>])${ATTRS}>`, 'gi');
//: Never text. The title is answered on its own, so it is not repeated in the text.
const DROP = /<(script|style|noscript|svg|template|title)(?=[\s/>])[\s\S]*?(?:<\/\1\s*>|$)/gi;
const BLOCKS = tag('p|div|section|article|header|footer|main|nav|aside|h[1-6]|ul|ol|dl|dt|dd|table|thead|tbody|tfoot|tr|pre|blockquote|figure|figcaption|form|fieldset|address|details|summary|caption|br|hr');
const CELLS = tag('td|th', { close: false });
const ITEMS = tag('li', { close: false });
const ANY_TAG = new RegExp(`<[a-zA-Z/!?]${ATTRS}>`, 'g');

/** Readable text from an HTML page: its title, and its body without scripts, styles, `noscript`,
 * `svg`, `template` or the head, links kept as their text, whitespace collapsed. */
export function htmlToText(html) {
  const found = /<title(?=[\s>])[^>]*>([\s\S]*?)<\/title\s*>/i.exec(html);
  const title = found ? collapse(decodeEntities(found[1].replace(ANY_TAG, ' '))).replace(/\s+/g, ' ').slice(0, 300) : '';
  let text = html.replace(/<!--[\s\S]*?(?:-->|$)/g, ' ');
  // The head: to its close, or to the body when the close is left out (it is optional).
  const head = /<head(?=[\s>])/i.exec(text);
  if (head) {
    const rest = text.slice(head.index);
    const end = /<\/head\s*>|<body(?=[\s>])/i.exec(rest);
    if (end) text = text.slice(0, head.index) + ' ' + rest.slice(end.index + (end[0][1] === '/' ? end[0].length : 0));
  }
  text = text.replace(DROP, ' ');
  text = text.replace(ITEMS, '\n- ').replace(CELLS, ' | ').replace(BLOCKS, '\n').replace(ANY_TAG, '');
  return { title, text: collapse(decodeEntities(text)) };
}

/** Spaces collapsed within lines, lines trimmed, at most one blank line in a row. */
function collapse(text) {
  return text
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t\f\v\u00a0\u2000-\u200b\u3000]+/g, ' ')
    .split('\n')
    .map(line => line.trim().replace(/^\|\s*/, ''))
    .join('\n')
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
  const place = await gate.webFetchReserve({ at: now(), agent });
  if (!place.ok) return json({ error: place.error, cap: place.cap }, place.status, { 'Retry-After': '3600' });

  const url = first.url.href;
  const signal = AbortSignal.timeout(timeoutMs);
  let current = first.url;
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
    const type = mediaType(upstream.headers.get('Content-Type'));
    if (!readable(type)) {
      await discard(upstream);
      return json({ error: `The page's content type ${type || '(none)'} is not one the gateway reads.`, url,
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
