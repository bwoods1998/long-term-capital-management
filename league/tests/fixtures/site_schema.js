// Shared browser/server boundary for /capital/: AI agents trading options on the Brokerage Account.
// Every published event and checkpoint passes these checks on the server before it is stored, and
// again in the browser before it is rendered. This file stays free of Node and DOM APIs so the
// Worker, the test runner and the page import the same rules.
//
// Schema 2 (Sept 26, 2026, the options swarm). The page starts over: one Brokerage Account, a swarm
// of agents in five bands, the Gym's pace, open structures, the ledger of real positions (Sept 28), the
// practice league (Sept 29), every input cost by part and the incubator route (Sept 30), and the tape of
// the agents' decisions.
// Every block is an allowlist: exact keys, typed values, nothing else. The data licenses behind the
// swarm (the option quote feeds) forbid publishing quotes, bids, asks, spreads, implied vols, greeks,
// surfaces or fitted parameters, so no block has a field for any of them, and every sentence an agent
// or the House writes must be quote-free (`quoteFree`): no decimal number, no dollar or cent price,
// and no number beside a quote word. The publisher masks them first; this refuses what it missed.

export const SCHEMA_VERSION = 2;
export const MAX_BATCH_BYTES = 512 * 1024;
export const MAX_CHECKPOINT_BYTES = 512 * 1024;
export const MAX_EVENTS_PER_BATCH = 100;
export const MAX_PAYLOAD_BYTES = 20 * 1024;
export const MAX_STRING_LENGTH = 8000;
export const MAX_EVENT_LIMIT = 200;
export const DEFAULT_EVENT_LIMIT = 50;
// The swarm's population ceiling is 96 living; the rest of the room is the recent dead.
export const MAX_AGENTS = 160;
export const MAX_STRUCTURES = 100;
export const MAX_SOCKETS = 200;
export const MAX_SOCKET_TAGS = 8;
export const MAX_PAYLOAD_DEPTH = 8;
export const MAX_PAYLOAD_KEYS = 100;
export const MAX_PAYLOAD_ITEMS = 500;

// ---------------------------------------------------------------------------- the words
// The agent's band, lowest first: Gym (training on recorded quotes), Candidate (passed the holdout;
// shadow trades only), Probe (real money, small), Sized (real money, sized by its forward record),
// Retired. The page uses these words as they are.
export const BANDS = ['gym', 'candidate', 'probe', 'sized', 'retired'];
export const REAL_BANDS = ['probe', 'sized'];
export const bandName = value => typeof value === 'string' && BANDS.includes(value);
// Every structure level 3 allows, all defined-risk.
export const STRUCTURE_TYPES = ['long_call', 'long_put', 'debit_vertical', 'credit_vertical', 'iron_condor', 'iron_butterfly',
  'long_butterfly', 'long_straddle', 'long_strangle', 'calendar', 'diagonal'];
export const structureType = value => typeof value === 'string' && STRUCTURE_TYPES.includes(value);
export const TRADE_ACTIONS = ['open', 'close'];

// The tape: the agents' decisions in their own words, their trades, the swarm's news, and the
// Brokerage Account's balance marks (which the Worker also archives as the balance history).
export const EVENT_KINDS = {
  'agent.note': { label: 'Note', tone: 'thought' },
  'agent.trade': { label: 'Trade', tone: 'trade' },
  'swarm.news': { label: 'Swarm', tone: 'swarm' },
  'account.mark': { label: 'Balance', tone: 'mark' },
};
export const FIXED_STREAMS = ['swarm', 'account'];
export const STREAM_FAMILIES = ['agent'];
// Public reading rooms only. No quote vendor and no brokerage host.
export const SOURCE_HOSTS = ['sec.gov', 'www.sec.gov', 'efts.sec.gov', 'blakewoods.us', 'github.com', 'finance.yahoo.com'];

const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
// Credential shapes never belong in a public payload, whatever else the text says.
const CREDENTIAL = /\bsk-|\bbearer[ :]|\bapca-/i;
const SCHEME = /[a-z][a-z0-9+.-]*:\/\/[^\s"'<>]*/gi;
// A scheme is only a scheme when something follows the colon: "from the data:\n" is prose.
const UNSAFE_SCHEME = /\b(?:javascript|vbscript|data|file|blob):(?=\S)/i;
const PAYLOAD_KEY = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$/;

// ------------------------------------------------------------------- quote-free sentences
// What an option quote looks like in prose: a decimal number (a price, an implied vol, a delta), a
// dollar or cent amount, or any number within a few characters of a quote word ("bid 3", "30 delta",
// "IV 18%", "a spread of 5"). `league/publish.py` (`scrub_quotes`) masks exactly these with "…"
// before it sends a sentence, so a masked sentence always passes; this is the site's own refusal of
// anything the publisher missed. Whole numbers elsewhere stay: "3 contracts", "45 DTE", "the 570 strike".
export const QUOTE_WORDS = ['bids?', 'asks?', 'offers?', 'mids?', 'midpoints?', 'nbbo', 'spreads?', 'wide', 'width', 'ivs?', 'implied',
  'vols?', 'volatility', 'skew', 'deltas?', 'gammas?', 'thetas?', 'vegas?', 'greeks?', 'premiums?', 'quotes?', 'quoted', 'prices?',
  'priced', 'pricing', 'marks?', 'cents?'];
const QUOTE_WORD = `(?:${QUOTE_WORDS.join('|')})`;
const DECIMAL = /\d\.\d/;
const DOLLARS = /\$\s?\d/;
const CENTS = /\d\s?¢/;
const WORD_THEN_NUMBER = new RegExp(`\\b${QUOTE_WORD}\\b[^\\d\\n.;]{0,16}\\d`, 'i');
const NUMBER_THEN_WORD = new RegExp(`\\d[%¢]?[\\s-]{0,2}${QUOTE_WORD}\\b`, 'i');
export const quoteFree = value => typeof value === 'string' && !DECIMAL.test(value) && !DOLLARS.test(value) && !CENTS.test(value)
  && !WORD_THEN_NUMBER.test(value) && !NUMBER_THEN_WORD.test(value);

// ------------------------------------------------------------------------- the scalars
export const exact = (value, fields) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));
export const plainObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export const agentId = value => typeof value === 'string' && /^[a-z0-9-]{1,40}$/.test(value);
export const slug = agentId;
// A test tape: a second, separate record served under /api/capital/t/<tape>/ and read by the page at
// /capital/?tape=<tape>, so a publisher can be tried end to end beside the real one. Only these names
// exist: any other is a 404 that wakes no object, so a visitor cannot mint records.
export const TAPES = ['test', 'canary'];
export const tapeName = value => typeof value === 'string' && TAPES.includes(value);
export const eventId = value => typeof value === 'string' && value.length >= 1 && value.length <= 200 && /^[A-Za-z0-9:_.-]+$/.test(value);
export const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const validStream = value => typeof value === 'string'
  && (FIXED_STREAMS.includes(value) || /^agent:[a-z0-9-]{1,40}$/.test(value));
export const streamFamily = value => validStream(value) ? (value.includes(':') ? value.slice(0, value.indexOf(':')) : value) : null;
export const streamAgent = value => validStream(value) && value.includes(':') ? value.slice(value.indexOf(':') + 1) : null;
export const validKind = value => typeof value === 'string' && Object.hasOwn(EVENT_KINDS, value);
// UTC with milliseconds, exactly what the publisher's now_iso() writes.
export const instant = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)
  && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
export const calendarDay = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00.000Z`)) && new Date(`${value}T00:00:00.000Z`).toISOString().slice(0, 10) === value;
export const decimal = (value, { signed = false, fraction = 8 } = {}) => typeof value === 'string' && value.length <= 32
  && new RegExp(`^${signed ? '-?' : ''}(?:0|[1-9]\\d{0,14})(?:\\.\\d{1,${fraction}})?$`).test(value);
export const money = value => decimal(value);
export const signedMoney = value => decimal(value, { signed: true });
export const counter = (value, max = 1000000000) => Number.isSafeInteger(value) && value >= 0 && value <= max;
export const integer = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;
export const nullable = (value, check) => value === null || check(value);
export const underlying = value => typeof value === 'string' && /^[A-Z][A-Z0-9.]{0,9}$/.test(value);
// The page names no venue (the owner, Sept 25, 2026: the account is "the Brokerage Account"), and neither
// does anything published to it: the publisher says "the broker" instead.
export const VENUE_NAMES = /alpaca|kalshi|coinbase/i;
const plainText = (value, max) => typeof value === 'string' && value.length <= max && !CONTROL.test(value) && !value.includes('<')
  && !VENUE_NAMES.test(value);
// Words a visitor reads: non-blank, bounded, no markup, no venue, and quote-free.
export const words = (value, max) => plainText(value, max) && value.trim().length > 0 && quoteFree(value);
// Words that may be empty: a reason nobody wrote is an empty string, not a lie.
export const prose = (value, max) => plainText(value, max) && quoteFree(value);
// A span of market time the Gym has simulated, in years with at most one decimal ("1284.5").
export const years = value => decimal(value, { fraction: 1 }) && Number(value) <= 100000000;
// Never dated more than a minute after the checkpoint that carries it (a minute of clock skew aside).
const notAfter = (at, publishedAt) => instant(at) && (publishedAt === undefined || Date.parse(at) <= Date.parse(publishedAt) + 60000);

// Only these hosts may appear in any published string, and only over https.
export function sourceUrl(value) {
  if (typeof value !== 'string' || value.length > 1000) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.port) return null;
    return SOURCE_HOSTS.includes(url.hostname) ? url.href : null;
  } catch { return null; }
}
export function safeString(value, max = MAX_STRING_LENGTH) {
  if (typeof value !== 'string' || value.length > max) return false;
  if (CONTROL.test(value) || value.includes('<') || CREDENTIAL.test(value) || UNSAFE_SCHEME.test(value)) return false;
  for (const match of value.match(SCHEME) || []) if (sourceUrl(match) === null) return false;
  return true;
}
// Private keys never leave the publisher. A leading underscore at any depth is a bug, not a filter.
export function safeValue(value, depth = 0) {
  if (depth > MAX_PAYLOAD_DEPTH) return false;
  if (value === null || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'string') return safeString(value);
  if (Array.isArray(value)) return value.length <= MAX_PAYLOAD_ITEMS && value.every(item => safeValue(item, depth + 1));
  if (typeof value !== 'object') return false;
  const keys = Object.keys(value);
  if (keys.length > MAX_PAYLOAD_KEYS) return false;
  return keys.every(key => !key.startsWith('_') && PAYLOAD_KEY.test(key) && safeValue(value[key], depth + 1));
}
export function byteLength(value) {
  const body = typeof value === 'string' ? value : JSON.stringify(value);
  if (typeof body !== 'string') return Infinity;
  return new TextEncoder().encode(body).length;
}
export function validPayload(payload, max = MAX_PAYLOAD_BYTES) {
  return plainObject(payload) && safeValue(payload) && byteLength(payload) <= max;
}

// ------------------------------------------------------------------------------ events
// Every kind carries one exact payload. An agent's note is its decision in its own words; a trade is
// one structure opened or closed (never a price: its maximum loss, and on a close its P&L); the
// swarm's news is the House's sentence about a birth, a band move or a retirement; a mark is one
// reading of the Brokerage Account.
export const TRADE_FIELDS = ['action', 'real', 'underlying', 'structure', 'legs', 'expiry', 'quantity', 'max_loss_usd', 'pnl_usd', 'why'];
export const KIND_PAYLOADS = {
  'agent.note': payload => exact(payload, ['text']) && words(payload.text, 2000),
  'agent.trade': payload => exact(payload, TRADE_FIELDS) && TRADE_ACTIONS.includes(payload.action) && typeof payload.real === 'boolean'
    && underlying(payload.underlying) && structureType(payload.structure) && integer(payload.legs, 1, 4) && calendarDay(payload.expiry)
    && integer(payload.quantity, 1, 10000) && nullable(payload.pnl_usd, signedMoney) && prose(payload.why, 240)
    // An open states what it can lose and has no result yet; a close states its result, and its maximum
    // loss only when the House still knows it.
    && (payload.action === 'open' ? money(payload.max_loss_usd) && payload.pnl_usd === null : nullable(payload.max_loss_usd, money)),
  // The sentence says what happened; `agent` says to whom (null for the House's own news), so an agent's
  // name is never inside words that the quote rule reads.
  'swarm.news': payload => exact(payload, ['agent', 'text']) && nullable(payload.agent, agentId) && words(payload.text, 300),
  'account.mark': payload => exact(payload, ['equity', 'cash', 'as_of']) && money(payload.equity) && money(payload.cash) && instant(payload.as_of),
};
export function validKindPayload(kind, payload) {
  return Object.hasOwn(KIND_PAYLOADS, kind) && plainObject(payload) && KIND_PAYLOADS[kind](payload);
}
export function validEvent(event) {
  try {
    if (!plainObject(event)) return false;
    const fields = ['id', 'stream', 'kind', 'at', 'payload', 'digest'];
    // The Worker's own seq is the only other key a stored event carries.
    if (!fields.every(field => Object.hasOwn(event, field))) return false;
    if (Object.keys(event).some(key => !fields.includes(key) && key !== 'seq')) return false;
    if (Object.hasOwn(event, 'seq') && !counter(event.seq, Number.MAX_SAFE_INTEGER)) return false;
    if (!eventId(event.id) || !validStream(event.stream) || !validKind(event.kind) || !instant(event.at) || !digest(event.digest)) return false;
    // A kind rides the stream its prefix names: agent.* on agent:<id>, swarm.* on swarm, account.* on account.
    if (event.kind.slice(0, event.kind.indexOf('.')) !== streamFamily(event.stream)) return false;
    return validPayload(event.payload) && validKindPayload(event.kind, event.payload);
  } catch { return false; }
}
export function validEventBatch(batch) {
  if (!exact(batch, ['schema_version', 'events'])) return false;
  if (batch.schema_version !== SCHEMA_VERSION || !Array.isArray(batch.events)) return false;
  if (batch.events.length < 1 || batch.events.length > MAX_EVENTS_PER_BATCH) return false;
  if (new Set(batch.events.map(event => event?.id)).size !== batch.events.length) return false;
  return batch.events.every(validEvent);
}
export function publicEvent(event) {
  return { seq: event.seq, id: event.id, stream: event.stream, kind: event.kind, at: event.at, payload: event.payload, digest: event.digest,
    ...(validDisplayName(event.display_name) ? { display_name: event.display_name } : {}) };
}
export function validPublicEvent(event) {
  if (!plainObject(event)) return false;
  const { display_name: displayName, ...original } = event;
  if (Object.hasOwn(event, 'display_name') && (!validDisplayName(displayName)
      || !((typeof event.stream === 'string' && event.stream.startsWith('agent:'))
        || (event.kind === 'swarm.news' && agentId(event.payload?.agent))))) return false;
  return counter(event.seq, Number.MAX_SAFE_INTEGER) && validEvent(original);
}

// The original twelve partners, in their original order. Ordinals are durable site-owned aliases:
// never reorder this list or use an alias as an execution identity.
export const PARTNER_NAMES = ['Meriwether', 'Hilibrand', 'Scholes', 'Rosenfeld', 'Haghani', 'Mullins',
  'McEntee', 'Krasker', 'Hawkins', 'Hufschmid', 'Huang', 'Leahy'];
export function displayNameFor(ordinal) {
  if (!Number.isSafeInteger(ordinal) || ordinal < 1) return null;
  const generation = Math.floor((ordinal - 1) / PARTNER_NAMES.length) + 1;
  return `${PARTNER_NAMES[(ordinal - 1) % PARTNER_NAMES.length]}${generation > 1 ? ` ${generation}` : ''}`;
}
export const validDisplayName = value => typeof value === 'string' && value.length <= 40
  && PARTNER_NAMES.some(name => new RegExp(`^${name}(?: [2-9]| [1-9][0-9]+)?$`).test(value));

// -------------------------------------------------------------------------- checkpoint
// Every block is present; a block not yet available is null and a list not yet filled is empty, so the
// first hours of a new House publish a checkpoint the page draws as "not yet".
export const CHECKPOINT_FIELDS = ['schema_version', 'published_at', 'run', 'account', 'performance', 'compute', 'gym', 'agents', 'structures'];

// Options trading alone: all realized cashflows plus marked open positions, supplied by the House.
// Optional for old schema-2 checkpoints; null P&L means the complete book could not be verified.
export function validTrading(value, publishedAt) {
  return exact(value, ['as_of', 'pnl_usd']) && notAfter(value.as_of, publishedAt) && nullable(value.pnl_usd, signedMoney);
}

// The run clock: when the House started on its new ledger (its first `ops.started`).
export function validRun(value, publishedAt) {
  return exact(value, ['started_at']) && nullable(value.started_at, at => notAfter(at, publishedAt));
}
// The Brokerage Account, read from the account itself. `stale` is true when the House could not
// refresh it and is republishing the last numbers it knows; the page then shows no profit.
export function validAccount(value, publishedAt) {
  return exact(value, ['equity', 'cash', 'as_of', 'stale']) && money(value.equity) && money(value.cash)
    && notAfter(value.as_of, publishedAt) && typeof value.stale === 'boolean';
}
// The profit basis: the account's equity at the reset, and the owner's deposits less withdrawals since,
// as verified from the account's own activity history (null until verified; both or neither).
export function validPerformance(value, publishedAt) {
  return exact(value, ['start_at', 'start_equity', 'net_flows', 'verified_at'])
    && instant(value.start_at) && Date.parse(value.start_at) <= Date.parse(publishedAt)
    && money(value.start_equity) && Number(value.start_equity) > 0
    && nullable(value.net_flows, signedMoney) && nullable(value.verified_at, instant)
    && (value.net_flows === null) === (value.verified_at === null)
    && (value.verified_at === null || (Date.parse(value.verified_at) >= Date.parse(value.start_at)
      && Date.parse(value.verified_at) <= Date.parse(publishedAt)));
}
// What the project has cost since the reset, part by part: Sail (models and boxes, as Sail billed them), Claude (the
// research roles' model calls), OpenAI, ThetaData, the market-data subscription, and anything else the run adds. A part
// not yet metered is null, and the page then shows no Net rather than a flattering one.
// Since Sept 30, 2026 Claude is its own part (`claude_usd`). A House before that publishes the older five parts: Claude
// inside `other_usd`, or nowhere at all (before #431), so the page cannot tell Claude's cost from that shape and shows no
// Net for it. Either shape validates, so either repository may deploy first.
export const COMPUTE_PARTS = ['sail_usd', 'claude_usd', 'openai_usd', 'thetadata_usd', 'market_data_usd', 'other_usd'];
export const LEGACY_COMPUTE_PARTS = COMPUTE_PARTS.filter(part => part !== 'claude_usd');
export const computeParts = value => (plainObject(value) && Object.hasOwn(value, 'claude_usd') ? COMPUTE_PARTS : LEGACY_COMPUTE_PARTS);
export function validCompute(value, publishedAt) {
  const parts = computeParts(value);
  return exact(value, ['as_of', ...parts]) && notAfter(value.as_of, publishedAt) && parts.every(part => nullable(value[part], money));
}
// A published decimal from an exact integer of 10^-8 dollars (`scaledAmount`), in the shortest form with at least cents.
export function scaledDecimal(amount) {
  const negative = amount < 0n;
  const size = negative ? -amount : amount;
  const fraction = (size % 100000000n).toString().padStart(8, '0').replace(/0{1,6}$/, '');
  return `${negative ? '-' : ''}${size / 100000000n}.${fraction}`;
}
// The older five parts for a page that validates them (the Worker's older reads): Claude back inside `other_usd`, as
// the House published it before Sept 30, 2026. Unknown when either is unknown.
export function legacyCompute(value) {
  if (!plainObject(value) || !Object.hasOwn(value, 'claude_usd')) return value;
  const { claude_usd: claude, ...rest } = value;
  return { ...rest, other_usd: claude === null || rest.other_usd === null ? null : scaledDecimal(scaledAmount(claude) + scaledAmount(rest.other_usd)) };
}
// The Gym's pace: programs tested (every evaluation is a trial), market-years simulated, and the
// families alive and retired. Never a result: those are derived from licensed quotes.
export function validGym(value, publishedAt) {
  return exact(value, ['as_of', 'trials', 'market_years', 'families_alive', 'families_retired']) && notAfter(value.as_of, publishedAt)
    && nullable(value.trials, counter) && nullable(value.market_years, years)
    && nullable(value.families_alive, count => counter(count, 100000)) && nullable(value.families_retired, count => counter(count, 1000000));
}
// A record of trades closed: how many, how many won, and the dollars (real money for `real`; the shadow
// book's hypothetical dollars for `forward`, the nightly replays and live shadow trades together).
export function validTally(value) {
  return exact(value, ['trades', 'wins', 'pnl_usd']) && counter(value.trades) && counter(value.wins) && value.wins <= value.trades
    && signedMoney(value.pnl_usd);
}
// An agent's record: its lineage's Gym evaluations (trials) and program versions (revisions), its
// forward record once it is a Candidate, and its real record once it trades real money.
export function validRecord(value) {
  return exact(value, ['trials', 'revisions', 'forward', 'real']) && counter(value.trials) && counter(value.revisions, 1000000)
    && nullable(value.forward, validTally) && nullable(value.real, validTally);
}
// One agent: one family (a mechanism, a structure and a slice of the universe), the mechanism in a
// sentence, its band and its record. The page names it from its id. Its program never publishes (its
// parameters are fitted to licensed data), nor does anything the program reads.
export const AGENT_FIELDS = ['id', 'family', 'mechanism', 'structure', 'band', 'born_at', 'retired_at', 'record'];
export const PROGRESS_KEYS = ['validation_run', 'validation_trades', 'validation_days', 'validation_mean', 'validation_t',
  'validation_dsr', 'validation_quarters', 'validation_stress', 'review', 'audit', 'holdout', 'real_structure',
  'credit_equity', 'risk_fit', 'forward_nonnegative', 'forward_trades', 'forward_mean', 'forward_confidence',
  'real_trades', 'probe_sessions', 'real_record', 'execution_ready'];
export const PROGRESS_COUNTS = ['validation_trades', 'validation_days', 'validation_quarters', 'forward_trades', 'real_trades', 'probe_sessions'];
const REAL_CHECKS = ['execution_ready', 'holdout', 'real_structure', 'credit_equity', 'risk_fit', 'forward_nonnegative'];
export const PROGRESS_CHECKS = {
  candidate: ['validation_run', 'validation_trades', 'validation_days', 'validation_mean', 'validation_t', 'validation_dsr',
    'validation_quarters', 'validation_stress', 'review', 'audit', 'holdout'],
  probe: REAL_CHECKS,
  sized: [...REAL_CHECKS, 'forward_trades', 'forward_mean', 'forward_confidence', 'real_trades', 'probe_sessions', 'real_record'],
  maintain: [...REAL_CHECKS, 'forward_trades', 'forward_mean', 'forward_confidence', 'real_record'],
};
// Validation needs: the owner's D2 line (Sept 26: 50 trades on 25 days) and the plan's earlier 100 on 60, so a
// checkpoint from either House release validates while the new line rolls out.
const PROGRESS_LIMITS = { validation_trades: [50, 100], validation_days: [25, 60], validation_quarters: [3, 3],
  forward_trades: [20, 1000], real_trades: [5, 50], probe_sessions: [1, 20] };
export const PROGRESS_BLOCKERS = ['validation_pending', 'evidence_stale', 'validation_failed', 'review_pending', 'review_failed',
  'audit_pending', 'audit_failed', 'holdout_pending', 'holdout_failed', 'look_limit', 'gate_paused', 'real_money_off',
  'grant_inactive', 'account_unavailable', 'structure_ineligible', 'equity_low', 'risk_too_large', 'forward_negative',
  'forward_incomplete', 'probe_incomplete', 'real_record_negative'];
export function validProgress(value, band) {
  const target = { gym: 'candidate', candidate: 'probe', probe: 'sized', sized: 'maintain' }[band];
  return exact(value, ['target', 'checks', 'blocked']) && Boolean(target) && value.target === target
    && nullable(value.blocked, reason => PROGRESS_BLOCKERS.includes(reason))
    && Array.isArray(value.checks) && value.checks.length === PROGRESS_CHECKS[target].length
    && value.checks.every((check, index) => exact(check, ['key', 'done', 'need']) && check.key === PROGRESS_CHECKS[target][index]
      && integer(check.need, ...(PROGRESS_LIMITS[check.key] || [1, 1])) && integer(check.done, 0, check.need));
}
export function validAgent(value, publishedAt, { publicRead = false } = {}) {
  if (!plainObject(value)) return false;
  const fields = Object.hasOwn(value, 'progress') ? [...AGENT_FIELDS, 'progress'] : AGENT_FIELDS;
  return (exact(value, fields) || (publicRead && exact(value, [...fields, 'display_name']) && validDisplayName(value.display_name)))
    && agentId(value.id) && slug(value.family) && prose(value.mechanism, 240)
    && nullable(value.structure, structureType) && bandName(value.band)
    && nullable(value.born_at, at => notAfter(at, publishedAt)) && nullable(value.retired_at, at => notAfter(at, publishedAt))
    && validRecord(value.record)
    && (!Object.hasOwn(value, 'progress') || nullable(value.progress, progress => validProgress(progress, value.band)));
}
// One open structure, held as one instrument: whose, on what, which kind, how many legs, its (nearest)
// expiry, how many, whether it is real money or the shadow book, its maximum loss and its P&L at the
// House's mark. Never a strike price, a leg price or anything else the quote feed said.
// A real structure may name its `route`: "incubator" (from Oct 1, 2026) is real money at tuition size, never evidence.
export const STRUCTURE_FIELDS = ['id', 'agent', 'underlying', 'structure', 'legs', 'expiry', 'quantity', 'real', 'opened_at', 'max_loss_usd', 'pnl_usd'];
export const STRUCTURE_ROUTES = ['incubator'];
export function validStructure(value, publishedAt) {
  const routed = plainObject(value) && Object.hasOwn(value, 'route');
  return exact(value, routed ? [...STRUCTURE_FIELDS, 'route'] : STRUCTURE_FIELDS) && (!routed || (STRUCTURE_ROUTES.includes(value.route) && value.real === true))
    && eventId(value.id) && agentId(value.agent) && underlying(value.underlying)
    && structureType(value.structure) && integer(value.legs, 1, 4) && calendarDay(value.expiry) && integer(value.quantity, 1, 10000)
    && typeof value.real === 'boolean' && notAfter(value.opened_at, publishedAt) && money(value.max_loss_usd) && nullable(value.pnl_usd, signedMoney);
}
// The older structure for a page that validates the exact fields (the Worker's older reads): no route.
export function legacyStructure(value) {
  if (!plainObject(value) || !Object.hasOwn(value, 'route')) return value;
  const { route: _route, ...rest } = value;
  return rest;
}
// ----------------------------------------------------------------------- the positions ledger
// Every real position on the Brokerage Account since the reset, open and closed: whose it was (an agent,
// or the House's own calibration round trips), what it was in words (root, structure kind, call or put),
// how many contracts, its expiry, when it opened and closed (to the minute), and its dollar P&L after fees
// (realized when closed, at the House's current value when open). No field is a strike, a fill price, a
// mark, a quote or anything else the quote feed said: the dollar result is the only number a row carries
// about money. An open row's P&L read with its maximum loss (published in `structures` and on the tape)
// implies its current value per contract: the ledger's public-data rules allow a position's dollar P&L.
//
// The rows, `earlier` (the positions not listed: the oldest closed past the table's length, and any the
// table's fields cannot describe), the account's other activity (fees no position carries, crypto fees,
// interest and the rest) and any unreconciled difference sum to `trading.pnl_usd` exactly, to the cent.
// A checkpoint whose ledger does not add up is refused whole, like any other malformed block: the House
// shows a difference it cannot explain as `unreconciled_usd`, never by leaving it out. While Profit is
// unknown, any line may be unknown too (an unpriced row, and so `earlier` holding it).
export const MAX_POSITIONS = 300;
// `incubator` (from Oct 1, 2026): an agent's position on the incubator route, real money at tuition size and never
// evidence. It names its agent, like an agent's row.
export const POSITION_SOURCES = ['agent', 'calibration', 'house', 'incubator'];
export const AGENT_SOURCES = ['agent', 'incubator'];
export const POSITION_RIGHTS = ['call', 'put', 'both'];
export const POSITION_STATUSES = ['open', 'closed'];
export const POSITION_FIELDS = ['id', 'source', 'agent', 'underlying', 'structure', 'right', 'legs', 'quantity', 'open_quantity', 'status',
  'expiry', 'opened_at', 'closed_at', 'pnl_usd'];
export const POSITIONS_FIELDS = ['as_of', 'rows', 'earlier', 'other', 'unreconciled_usd'];
export const EARLIER_FIELDS = ['positions', 'pnl_usd'];
export const OTHER_PARTS = ['fees_usd', 'crypto_usd', 'interest_usd', 'misc_usd'];
// Which side a structure can be on: a vertical, a butterfly, a calendar or a diagonal is all calls or all
// puts; a condor, an iron butterfly, a straddle and a strangle are both.
const SINGLE_RIGHT = ['call', 'put'];
export const STRUCTURE_RIGHTS = {
  long_call: ['call'], long_put: ['put'], debit_vertical: SINGLE_RIGHT, credit_vertical: SINGLE_RIGHT, iron_condor: ['both'],
  iron_butterfly: ['both'], long_butterfly: SINGLE_RIGHT, long_straddle: ['both'], long_strangle: ['both'], calendar: SINGLE_RIGHT,
  diagonal: SINGLE_RIGHT,
};
// A ledger amount is whole cents, so its sum is exact.
export const centsAmount = value => signedMoney(value) && /^-?\d+(?:\.\d{1,2})?$/.test(value);
// A published decimal as an exact integer of 10^-8 dollars, for sums that never touch a float.
export function scaledAmount(value) {
  const negative = value.startsWith('-');
  const [whole, fraction = ''] = (negative ? value.slice(1) : value).split('.');
  const amount = BigInt(whole) * 100000000n + BigInt((fraction + '00000000').slice(0, 8));
  return negative ? -amount : amount;
}
export const positionId = value => typeof value === 'string' && /^real:\d{1,12}$/.test(value);
// A ledger time is to the minute: the page shows minutes, and a broker's fill time to the millisecond would be a
// lookup key into the public time and sales, which name the strike and the price.
export const minuteInstant = value => instant(value) && value.endsWith(':00.000Z');
export function validPosition(value, publishedAt, { publicRead = false } = {}) {
  if (!plainObject(value)) return false;
  // The site's partner name rides a public read, and only on a row that names an agent.
  const named = publicRead && Object.hasOwn(value, 'display_name');
  if (!exact(value, named ? [...POSITION_FIELDS, 'display_name'] : POSITION_FIELDS)) return false;
  if (named && (!AGENT_SOURCES.includes(value.source) || !validDisplayName(value.display_name))) return false;
  const open = value.status === 'open';
  return positionId(value.id) && POSITION_SOURCES.includes(value.source)
    && (AGENT_SOURCES.includes(value.source) ? agentId(value.agent) : value.agent === null)
    && underlying(value.underlying) && structureType(value.structure) && STRUCTURE_RIGHTS[value.structure].includes(value.right)
    && integer(value.legs, 1, 4) && integer(value.quantity, 1, 10000) && integer(value.open_quantity, 0, value.quantity)
    && POSITION_STATUSES.includes(value.status) && calendarDay(value.expiry) && notAfter(value.opened_at, publishedAt) && minuteInstant(value.opened_at)
    // Open holds at least one contract and has not closed; closed holds none and closed after it opened.
    && (open ? value.open_quantity >= 1 && value.closed_at === null
      : value.open_quantity === 0 && notAfter(value.closed_at, publishedAt) && minuteInstant(value.closed_at)
        && Date.parse(value.closed_at) >= Date.parse(value.opened_at))
    && nullable(value.pnl_usd, centsAmount);
}
// The older row for a page that knows only the first three sources (the Worker's older reads): an incubator row reads
// as its agent's, which it is. Profit and the sum are unchanged.
export const legacyPosition = value => (plainObject(value) && value.source === 'incubator' ? { ...value, source: 'agent' } : value);
// Unknown (null) only while Profit is: `validPositions` requires every line once Profit is known.
export const validEarlier = value => exact(value, EARLIER_FIELDS) && integer(value.positions, 1, 1000000000) && nullable(value.pnl_usd, centsAmount);
export const validOther = (value, publishedAt) => exact(value, ['as_of', ...OTHER_PARTS]) && notAfter(value.as_of, publishedAt)
  && OTHER_PARTS.every(part => centsAmount(value[part]));
// Every amount the ledger adds up to Profit, in the order the page lists them.
export function ledgerAmounts(value) {
  return [...value.rows.map(row => row.pnl_usd), value.earlier ? value.earlier.pnl_usd : '0',
    ...OTHER_PARTS.map(part => value.other?.[part] ?? null), value.unreconciled_usd];
}
export function validPositions(value, trading, publishedAt, { publicRead = false } = {}) {
  if (!exact(value, POSITIONS_FIELDS) || !plainObject(trading) || value.as_of !== trading.as_of || !notAfter(value.as_of, publishedAt)) return false;
  const { rows } = value;
  if (!Array.isArray(rows) || rows.length > MAX_POSITIONS || new Set(rows.map(row => row?.id)).size !== rows.length
    || !rows.every(row => validPosition(row, publishedAt, { publicRead }))) return false;
  if (!nullable(value.earlier, validEarlier) || !nullable(value.other, other => validOther(other, publishedAt))
    || !nullable(value.unreconciled_usd, centsAmount)) return false;
  // An unknown Profit leaves unknown lines unknown. A known one is their exact sum, and every line is known.
  if (trading.pnl_usd === null) return true;
  const amounts = ledgerAmounts(value);
  if (amounts.some(amount => amount === null)) return false;
  return amounts.reduce((sum, amount) => sum + scaledAmount(amount), 0n) === scaledAmount(trading.pnl_usd);
}

// ----------------------------------------------------------------------- the practice league
// Every family practising on live quotes in the House's shadow book under the Gym's fill rules (Sept 29, 2026): never
// real money, never Profit, never the positions ledger or a forward record. One row per family: its agent, lineage,
// structure kind, tier (it practised a validated version, or an eligible Train version), whether its agent is alive,
// sessions, closed trades, wins, realized P&L after fees (whole cents) and return on maximum loss (two places). Never
// a price, strike, leg, expiry, minute, trade date, version, code, parameter or Validation figure. `totals` are over
// every family, shown or not; when every family is shown they are exactly the rows' sums.
export const MAX_PRACTICE_ROWS = 48;
export const PRACTICE_TIERS = ['validated', 'train'];
export const PRACTICE_STATUSES = ['alive', 'retired'];
export const PRACTICE_FIELDS = ['as_of', 'sessions', 'capital_usd', 'totals', 'rows'];
export const PRACTICE_TOTALS = ['families', 'trades', 'wins', 'pnl_usd'];
export const PRACTICE_ROW_FIELDS = ['agent', 'family', 'structure', 'tier', 'status', 'sessions', 'trades', 'wins', 'pnl_usd', 'return_on_risk'];
const returnOnRisk = value => decimal(value, { signed: true, fraction: 2 }) && Math.abs(Number(value)) < 1000;
export function validPracticeRow(value, { publicRead = false } = {}) {
  if (!plainObject(value)) return false;
  const named = publicRead && Object.hasOwn(value, 'display_name');
  return exact(value, named ? [...PRACTICE_ROW_FIELDS, 'display_name'] : PRACTICE_ROW_FIELDS) && (!named || validDisplayName(value.display_name))
    && agentId(value.agent) && slug(value.family) && nullable(value.structure, structureType)
    && PRACTICE_TIERS.includes(value.tier) && PRACTICE_STATUSES.includes(value.status)
    && counter(value.sessions, 10000) && counter(value.trades) && counter(value.wins) && value.wins <= value.trades
    && centsAmount(value.pnl_usd) && nullable(value.return_on_risk, returnOnRisk);
}
export function validPractice(value, publishedAt, { publicRead = false } = {}) {
  if (!exact(value, PRACTICE_FIELDS) || !notAfter(value.as_of, publishedAt) || !counter(value.sessions, 10000)
    || !(centsAmount(value.capital_usd) && money(value.capital_usd) && scaledAmount(value.capital_usd) > 0n)) return false;
  const { totals, rows } = value;
  if (!exact(totals, PRACTICE_TOTALS) || !counter(totals.families, 1000000) || !counter(totals.trades) || !counter(totals.wins)
    || totals.wins > totals.trades || !centsAmount(totals.pnl_usd)) return false;
  if (!Array.isArray(rows) || rows.length > MAX_PRACTICE_ROWS || new Set(rows.map(row => row?.agent)).size !== rows.length
    || !rows.every(row => validPracticeRow(row, { publicRead }))) return false;
  const trades = rows.reduce((sum, row) => sum + row.trades, 0);
  const wins = rows.reduce((sum, row) => sum + row.wins, 0);
  if (totals.families < rows.length || totals.trades < trades || totals.wins < wins) return false;
  if (totals.families > rows.length) return true;
  return totals.trades === trades && totals.wins === wins
    && rows.reduce((sum, row) => sum + scaledAmount(row.pnl_usd), 0n) === scaledAmount(totals.pnl_usd);
}

// Blocks a newer House adds, each optional so an older House's checkpoint still validates: Profit (`trading`), the
// positions ledger beside it, and the practice league.
export const OPTIONAL_CHECKPOINT_FIELDS = ['trading', 'positions', 'practice'];
export function validCheckpoint(checkpoint, { publicRead = false } = {}) {
  try {
    if (!plainObject(checkpoint) || !CHECKPOINT_FIELDS.every(field => Object.hasOwn(checkpoint, field))
      || !Object.keys(checkpoint).every(key => CHECKPOINT_FIELDS.includes(key) || OPTIONAL_CHECKPOINT_FIELDS.includes(key))
      || (Object.hasOwn(checkpoint, 'positions') && !Object.hasOwn(checkpoint, 'trading'))) return false;
    const at = checkpoint.published_at;
    if (checkpoint.schema_version !== SCHEMA_VERSION || !instant(at)) return false;
    if (!validRun(checkpoint.run, at)) return false;
    if (!nullable(checkpoint.account, value => validAccount(value, at))) return false;
    if (!nullable(checkpoint.performance, value => validPerformance(value, at))) return false;
    if (!nullable(checkpoint.compute, value => validCompute(value, at))) return false;
    if (!nullable(checkpoint.gym, value => validGym(value, at))) return false;
    if (Object.hasOwn(checkpoint, 'trading') && !nullable(checkpoint.trading, value => validTrading(value, at))) return false;
    // The ledger is optional (a House that predates it sends none) and needs the Profit it sums to.
    if (Object.hasOwn(checkpoint, 'positions')
      && !nullable(checkpoint.positions, value => validPositions(value, checkpoint.trading, at, { publicRead }))) return false;
    if (Object.hasOwn(checkpoint, 'practice') && !nullable(checkpoint.practice, value => validPractice(value, at, { publicRead }))) return false;
    const { agents, structures } = checkpoint;
    if (!Array.isArray(agents) || agents.length > MAX_AGENTS || new Set(agents.map(agent => agent?.id)).size !== agents.length
      || !agents.every(agent => validAgent(agent, at, { publicRead }))) return false;
    if (!Array.isArray(structures) || structures.length > MAX_STRUCTURES || new Set(structures.map(row => row?.id)).size !== structures.length
      || !structures.every(row => validStructure(row, at))) return false;
    return byteLength(checkpoint) <= MAX_CHECKPOINT_BYTES;
  } catch { return false; }
}

// ------------------------------------------------------------------------- the live tape
// A socket receives an event when it subscribed to that exact stream, or to everything.
export function socketMatches(tags, stream) {
  return Array.isArray(tags) && (tags.includes('all') || tags.includes(stream));
}
export function parseStreamTags(value) {
  if (value === null || value === undefined || value === '') return ['all'];
  if (typeof value !== 'string' || value.length > 400) return null;
  const tags = [...new Set(value.split(',').map(part => part.trim()).filter(Boolean))];
  if (!tags.length || tags.length > MAX_SOCKET_TAGS) return null;
  if (!tags.every(tag => tag === 'all' || validStream(tag))) return null;
  return tags.includes('all') ? ['all'] : tags;
}
