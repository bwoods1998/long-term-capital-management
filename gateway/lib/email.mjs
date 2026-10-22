// The only human touch this floor is designed to need. Six things can put a message in the
// owner's inbox, each at most once every six hours, and five of them are "something is wrong and
// I could not fix it myself". The sixth is the evening digest.
//
// Composition is pure and lives here so every subject and every line of every alert is checked by
// the test suite rather than discovered in production. Nothing composed here can contain a
// credential: the facts that reach it are numbers, a box status, a short failure code, and (for an
// interrupted box) ids, names and times each kept only in its own shape and the provider's sentence
// cut to plain words with any token-shaped run redacted (`lib/sail.mjs` `boxStatus`).

export const ALERT_KINDS = [
  'sail_balance_low',
  'sail_balance_critical',
  'floor_stopped',
  'box_not_running',
  'box_interrupted',
  'kill_switch_engaged',
  'caps_exhausted',
  'daily_digest',
];

//: Where Sail's docs send a person for help with a Sailbox ("Getting Help": the Sail community Slack, where the Sail team
//: answers), and that page.
export const SAIL_SLACK = 'https://join.slack.com/t/sailresearchcrew/shared_invite/zt-41pdcym9j-UU0Ey~A~r6n2H0DQVQsQHQ';
export const SAIL_HELP = 'https://docs.sailresearch.com/sailboxes-getting-help';

export const FROM = 'agent@blakewoods.us';
export const TO = 'blakewoods98@gmail.com';
export const CONSOLE = 'https://app.sailresearch.com/';
export const FLOOR = 'https://blakewoods.us/capital/';

const money = value => (Number.isFinite(value) ? `$${Number(value).toFixed(2)}` : 'unknown');
const days = value => (Number.isFinite(value) ? `${value < 10 ? value.toFixed(1) : Math.floor(value)} days` : 'an unknown time');
const when = value => (typeof value === 'string' && value ? value.slice(0, 16).replace('T', ' ') + ' UTC' : 'an unknown date');
const runwayLines = facts => [
  `Sail credit: ${money(facts.balance_usd)}; ${money(facts.spendable_usd)} of it is above the ${money(facts.reserve_usd)} reserve.`,
  `The floor is burning about ${money(facts.burn_usd_per_day)} a day (models and the box), so the credit lasts ${days(facts.runway_days)}, to about ${when(facts.run_out_at)}.`,
  'Runway is advisory: research, shadow testing and live desks continue above the reserve. There is no runway-based throttle or floor-wide daily spending cap.',
  'At the reserve, new model work pauses; order monitoring and settlements continue. Adding Sail credit resumes model work automatically after the balance refresh.',
];
const signed = value => (Number.isFinite(value) ? `${value < 0 ? '-' : '+'}$${Math.abs(value).toFixed(2)}` : 'unknown');
const number = value => (Number.isFinite(value) ? String(value) : 'unknown');

/** `{ subject, text }` for one alert. `facts` is whatever the watchdog pass learned. */
export function compose(kind, facts = {}) {
  const lines = [];
  let subject;
  switch (kind) {
    case 'sail_balance_low':
      subject = `LTCM: ${days(facts.runway_days)} of Sail credit left — top up when you can`;
      lines.push(...runwayLines(facts));
      break;
    case 'sail_balance_critical':
      subject = `LTCM: ${days(facts.runway_days)} of Sail credit left — top up now`;
      lines.push(
        ...runwayLines(facts),
        'Top up before the reserve is reached to keep model work uninterrupted. This warning does not slow the floor.',
      );
      break;
    case 'floor_stopped':
      subject = 'LTCM: the desks have stopped — Sail credit is at the reserve';
      lines.push(
        `Sail credit is ${money(facts.balance_usd)}, at or under the ${money(facts.reserve_usd)} reserve.`,
        'No new desk session starts. Marks, order polling, settlements and publication continue; open orders rest at the venues.',
        'Add credit at Sail and the floor resumes on its own after the balance refresh. Nothing else is needed.',
      );
      break;
    case 'disk_low':
      subject = 'LTCM: the floor box is running out of disk';
      lines.push(
        `The Sailbox has ${number(facts.free_gb)} GiB free${facts.total_gb ? ` of ${number(facts.total_gb)} GiB` : ''} under ${facts.root || '/workspace'}.`,
        facts.detail || 'The floor trimmed its caches. If the space keeps falling the loop stops when the disk is full.',
        'Find the culprit on the box (du -xsh /workspace/.data/ltcm/* /state/* /tmp /var/*) and free or grow the disk before the loop dies.',
      );
      break;
    case 'box_not_running':
      subject = 'LTCM: the desks are not running';
      lines.push(
        `The Sailbox is ${facts.box_status || 'not reachable'} and the gateway could not bring it back.`,
        facts.published_at
          ? `The last published checkpoint is ${facts.published_at} (${number(facts.age_seconds)}s old).`
          : 'No checkpoint has been published.',
        facts.detail ? `Last failure: ${facts.detail}.` : 'The restart was attempted and did not confirm.',
        'Venue credentials are unaffected: they live in the gateway, not on the box.',
      );
      break;
    case 'box_interrupted': {
      // Oct 14, 2026: an AWS spot interruption left the House `interrupted_restorable` for seven hours; every resume hung
      // and only the Sail team could restore it. One message an interruption, with the words to post.
      const box = facts.box_id || 'the House box';
      const status = facts.box_status || 'interrupted_restorable';
      const since = when(facts.status_since || facts.first_seen_at);
      const what = facts.error_message ? `"${facts.error_message}"` : 'no reason given';
      const tries = Number.isSafeInteger(facts.tries) ? facts.tries : 0;
      const last = facts.last_answer || 'unknown';
      const outcome = last === 'timeout' ? 'timed out with no answer' : `answered ${last}`;
      subject = 'LTCM: the House box was interrupted and has not come back — ask Sail on Slack';
      lines.push(
        `The Sailbox ${box} is ${status} since ${since} (${what}). The gateway asked Sail to restore it ${tries} `
          + `time${tries === 1 ? '' : 's'} since ${when(facts.first_seen_at)}; the last call ${outcome}.`,
        `Only Sail can bring it back. Sail's docs ("Getting Help", ${SAIL_HELP}) send you to their community Slack: ${SAIL_SLACK}`,
        'Post this, as it is:',
        '',
        `> Sailbox ${box} (app ${facts.app_name || 'unknown'}, ${facts.app_id || 'app id unknown'}, name ${facts.box_name || 'unknown'}) `
          + `went ${status} at ${since} (${what}; last_checkpointed_at ${facts.last_checkpointed_at || 'unknown'}, `
          + `checkpoint_generation ${number(facts.checkpoint_generation)}). Since ${when(facts.first_seen_at)} our watchdog's `
          + `POST /v1/sailboxes/{id}/resume (REST, ${tries} tries, the last at ${when(facts.last_try_at)}) has not brought it `
          + `back: the last call ${outcome}; GET /v1/sailboxes/{id} answers. Please restore it from its last checkpoint on the same id. It runs `
          + 'a live trading daemon on a real account, so a fork to a second box is not an option for us.',
        '',
        'Do not fork the box or start another from a checkpoint: a resume still queued could bring this one back beside it, '
          + 'and two Houses would trade one account.',
        `The watchdog keeps asking Sail every ${number(facts.cooldown_minutes)} minutes (at most ${number(facts.max_tries)} tries) `
          + 'and sends nothing more about this interruption. Open orders rest at the venue; the kill switch and the caps are unchanged.',
        'Venue credentials are unaffected: they live in the gateway, not on the box.',
      );
      break;
    }
    case 'kill_switch_engaged':
      subject = 'LTCM: the order gateway kill switch is engaged';
      lines.push(
        'No orders are being forwarded to any venue. Reads and cancels still pass.',
        'The desks keep researching and keep their books; they simply cannot open a position.',
        'Release it with a POST to /v1/unkill on the gateway.',
      );
      break;
    case 'caps_exhausted':
      subject = "LTCM: today's order caps are used up";
      lines.push(
        `The floor has placed ${number(facts.orders)} orders for ${money(facts.notional_usd)} today.`,
        `The caps are ${number(facts.max_day_orders)} orders and ${money(facts.max_day_usd)} a day.`,
        'Further orders are refused until the next trading day. Nothing is wrong; this is the cap working.',
      );
      break;
    case 'daily_digest':
      // Profit since the reset replaces the day's P&L (Sept 26, 2026 (the options-swarm run, Wave 5)): the schema-2
      // checkpoint's equity less its start equity less the owner's net deposits, or unknown when any part is missing.
      subject = `LTCM daily: equity ${money(facts.equity_usd)}, profit since the reset ${signed(facts.profit_usd)}`;
      lines.push(
        `Equity: ${money(facts.equity_usd)}${facts.equity_stale ? ' (the broker reading is stale)' : ''}.`,
        `Profit since the reset: ${signed(facts.profit_usd)} (equity less the start equity and the owner's net deposits).`,
        `Orders through the gateway today: ${number(facts.orders)} for ${money(facts.notional_usd)}.`,
        `Sail balance: ${money(facts.balance_usd)}; spend over ${facts.range || 'the window'}: ${money(facts.spend_usd)}; runway ${days(facts.runway_days)}.`,
        `Box: ${facts.box_status || 'unknown'}. Kill switch: ${facts.kill_switch ? 'engaged' : 'open'}.`,
        facts.published_at ? `Checkpoint published ${facts.published_at}.` : 'No checkpoint has been published.',
      );
      break;
    default:
      return null;
  }
  lines.push('', FLOOR, CONSOLE);
  return { subject, text: lines.filter(line => line !== undefined && line !== null).join('\n') + '\n' };
}

// What the floor may post to /v1/notify: fills, settlements, the sample, a disk warning, a real-money stop, a funding
// cliff (V3-A, WP8: the budget rule's card notice, league/ops/budget.py), a stall (the owner's goal of Oct 7, 2026,
// item 6: the House's `stall` job, league/ops/stall.py), and the event lane's daily one-screen report (release 1019c,
// the goal of Oct 19, 2026, item 5: league/ops/daily_report.py, sent by the stall job once a New York day). Deploy the
// gateway first: an older one answers 400 to a kind it does not know, and nothing is mailed.
export const NOTICE_KINDS = ['trade', 'settled', 'test', 'disk_low', 'live_stop', 'funding', 'stall', 'report'];
//: The causes a stall notice may name (league/ops/stall.py CAUSES) and the words its subject gives each. A cause not named
//: here is not composed (a 400): the subject carries only these words, never the House's text.
export const STALL_CAUSES = {
  births: 'no births',
  gym_runs: 'too few Gym runs',
  validations: 'no Validation verdicts',
  braked: 'the Sail guard braked most of the day',
  runway_sail: 'Sail research runway short',
  runway_claude: 'Claude research runway short',
  owner_deploy: 'an owner deploy is waiting',
  paused: 'the floor is paused',
  grant_refused: 'the standing grant refused to re-ratify',
  kill_on: 'the kill switch is on',
  // Oct 10, 2026 (the readiness audit's M6): the direction lane's alarms and K5, a Done checkpoint that holds (news the
  // owner hears at once), a pre-open FAIL and a late or stopped nightly. The House sends these only once this gateway
  // knows them: deploy the gateway first (a cause not named here makes the whole notice a 400, nothing mailed).
  dlane: 'a direction-lane alarm',
  done: 'a Done checkpoint holds',
  preopen: 'a pre-open check failed',
  forward: 'the nightly forward replay is late or stopped',
  // Oct 10, 2026 (the no-captain audit): the architect bears (almost) nothing while it keeps asking, the swarm's own
  // alerts (reader_cut, agenda_guard, gate_coverage...) that reached only its ledger, and research under its budget or
  // bound by a setting. Deploy the gateway first, as above.
  birth_yield: 'few births while the architect keeps asking',
  swarm_alerts: 'the swarm raised alerts',
  underspend: 'research under its budget or bound by a setting',
  // Oct 11, 2026 (release E2.4): the equity lanes' own causes (league/ops/elane_health.py), which no alarm watched in
  // their first hours: most scored versions unjudged for a fault of their own program, equity passes that bear no
  // family, work owed and not done (nothing scored for hours, or most Train steps skipped for want of model dollars)
  // and most programs refused before a run by one static rule. Each keys its own notice. Deploy the gateway first, as
  // above.
  elane_dq: 'most equity versions could not be judged',
  elane_births: 'the equity passes bear no family',
  elane_idle: 'the equity lanes are idle or starved',
  elane_refused: 'most equity programs refused before a run by one rule',
  // Oct 19, 2026 (release 1019c, the goal of Oct 19, item 5: "alarms on stalls, missed events, fill gaps and cap
  // breaches"): the day's MEASURED metered compute over its cap (league/ops/metered.py), and the event lane's own four
  // (league/ops/evl_health.py), judged by progress: no clean record pass in 30 minutes (a feed erroring), a decision not
  // made in its window, verdicts unanswered past their decision, intents left open after the night's score. Deploy the
  // gateway first, as above.
  cap_breach: 'metered compute went over the day\'s cap or could not be measured',
  evl_record: 'the event lane read no feed cleanly for 30 minutes',
  evl_decide: 'an event-lane decision missed its window',
  evl_verdicts: 'event-lane verdicts went unanswered',
  evl_score: 'event-lane intents were left unsettled',
  // The goal's "fill gaps": the lane's real fills off the shadow's own auction prints by more than 15 bp either way (the
  // signed mean of a side over the last 20 priced fills: the House's event twins; worse or better, the House says).
  evl_fills: 'event-lane fills strayed from the auction prices',
  // A84 (release 1019f): a seatable program's final record (league/events/screen.py `final_until`, what every look waits
  // for) more than one session behind what A69's fast path allows; the House names the program and the judge's why.
  // Deploy the gateway first, as above.
  evl_final: 'event-lane looks wait longer than the fast path allows',
  // Release 1019f (the audit of the live House, lens "stalls": alarms that did not exist): the real buys of an auction
  // that never became fills (under 90% filled, or one never sent: the venue's cancels at once, A80, and the constraint
  // that bound), the daily-index backfill late or failing (the screen's looks wait on it), and real fills the book owes
  // the lane's own record. Deploy the gateway first, as above.
  evl_entries: 'event-lane real buys went unfilled or unsent',
  evl_backfill: 'the event lane\'s daily-index backfill is late or failing',
  evl_handback: 'real event fills are missing from the lane\'s record',
  // PREREG-EVL-7 (release 1019i): the learners' own stalls (league/ops/evl_learner.py, judged only once the freeze pins
  // REGISTERED_AT_7): a live part that failed or ran past its own bound (never traded at that auction), a decision owed,
  // a training lagging the evening score, a nightly recompute mismatch, a warm-up unmet. Deploy the gateway first, as
  // above: an older gateway refuses a notice naming a cause it does not word.
  evl_learner: 'the event lane\'s learners failed, lagged or mismatched',
};
//: The most figures a stall notice lists for one cause, and the shape of a figure's name.
const STALL_NUMBERS = 16;
//: The most characters of an owner step the mail carries.
const STALL_STEP_CHARS = 400;
const FIGURE_NAME = /^[a-z][a-z0-9_]{0,39}$/;
const TOKEN = /^[a-z0-9_.,:-]{1,80}$/;
//: The meters a funding notice may name (league/ops/budget.py): Sail's prefund and the Anthropic account.
export const FUNDING_METERS = { sail: 'Sail', claude: 'Claude (Anthropic)' };
//: The stops the House trips on real money (Sept 26, 2026 (the options-swarm run, Wave 5)). A stop not named here is not
//: composed (a 400): a subject names only these words.
export const LIVE_STOPS = ['drawdown', 'daily', 'reconciliation', 'assignment'];
export const RELEASE_DRAWDOWN = 'Exits go on; the Gym keeps running. Release the drawdown pause on the box with python3 -m league.live --root /workspace/state --release-drawdown.';
const DECIMAL = /^-?\d{1,12}(\.\d{1,6})?$/;
//: A dollar figure or a count of days the House sent as a string or a number: echoed only when it reads as a decimal.
const decimal = value => {
  const text = typeof value === 'number' && Number.isFinite(value) ? String(value) : value;
  return typeof text === 'string' && DECIMAL.test(text) ? text : null;
};
const dollars = value => (decimal(value) === null ? 'unknown' : `$${Number(decimal(value)).toFixed(2)}`);
const dayCount = value => (decimal(value) === null ? 'unknown' : `${Number(decimal(value))}`);
const DATE = /^\d{4}-\d{2}-\d{2}(T[0-9:.]{2,15}Z)?$/;
const dateOf = value => (typeof value === 'string' && DATE.test(value) ? value.slice(0, 10) : 'unknown');
const clip = (value, max) => (typeof value === 'string' ? value.slice(0, max) : '');
//: The House's own sentence, on one line: control characters (a newline included) become one space.
const sentence = (value, max) => clip(value, max).replace(/[\x00-\x1f\x7f]+/g, ' ').trim();
//: A stall's figure as the House sent it: a decimal, a date or time, yes or no, a short lower-case token, else unknown.
const figure = value => {
  if (value === true || value === false) return value ? 'yes' : 'no';
  if (decimal(value) !== null) return decimal(value);
  if (typeof value === 'string' && DATE.test(value)) return value;
  if (typeof value === 'string' && TOKEN.test(value)) return value;
  return 'unknown';
};
const price = value => (typeof value === 'string' && value ? `$${value}` : 'unknown');

/**
 * A stall notice's causes (league/ops/stall.py `notice_facts`: `causes`, each `cause_facts`), each with its owner step
 * cut to one line (`step`, '' when none), or null when the list is not one to compose: not a list, empty, longer than
 * STALL_CAUSES, an entry that is not an object, a cause STALL_CAUSES does not name, or a cause named twice.
 */
export function stallEntries(facts = {}) {
  const causes = facts?.causes;
  if (!Array.isArray(causes) || causes.length < 1 || causes.length > Object.keys(STALL_CAUSES).length) return null;
  const seen = new Set();
  const out = [];
  for (const entry of causes) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
    if (typeof entry.cause !== 'string' || !Object.hasOwn(STALL_CAUSES, entry.cause) || seen.has(entry.cause)) return null;
    seen.add(entry.cause);
    out.push({ entry, cause: entry.cause, step: sentence(entry.owner_step, STALL_STEP_CHARS) });
  }
  return out;
}

/**
 * The dedupe key of a stall notice, whatever id the House sent (the router's; the Gate keeps it STALL_NOTICE_MS or
 * STALL_INFO_MS): `stall:owner:<the owner causes, sorted, joined by +>` when some cause carries an owner step, so a
 * new one is mailed at once and the same ones at most every 12 hours; `stall:info:<every cause, sorted, joined by +>`
 * when none does, so the same causes are mailed at most every 24 hours and a new one at once (the review of the
 * no-captain build, Oct 10, 2026: one cause standing for days held every new one back up to a day). Null when the
 * notice is not one to compose.
 */
export function stallKey(facts = {}) {
  const entries = stallEntries(facts);
  if (!entries) return null;
  const owner = entries.filter(item => item.step).map(item => item.cause).sort();
  return owner.length ? `stall:owner:${owner.join('+')}` : `stall:info:${entries.map(item => item.cause).sort().join('+')}`;
}

//: THE DAILY ONE-SCREEN REPORT (release 1019c; league/ops/daily_report.py `facts`): one screen on a phone, so no line is
//: longer than REPORT_WIDTH characters. The House sends FIGURES ONLY and this composes every word: a count, a dollar,
//: basis-point or percent figure, a day (YYYY-MM-DD) or HH:MM, a program's own pre-registered `EVL-...` id (shown without
//: its EVL- prefix), a band's name, a stall cause's id (worded by STALL_CAUSES). No headline, no document text, no
//: symbol, no price is ever echoed: anything else where a figure goes reads "unknown" or "n/a", and a program whose id
//: is not one is left out.
export const REPORT_WIDTH = 60;
export const REPORT_PROGRAMS = 32;
const PROGRAM_ID = /^EVL-[A-Z0-9][A-Z0-9-]{0,47}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const HHMM = /^\d{2}:\d{2}$/;
const BANDS = ['learning', 'probe', 'sized', 'retired'];
const plain = value => (value && typeof value === 'object' && !Array.isArray(value) ? value : {});
const list = value => (Array.isArray(value) ? value : []);
const real = value => (typeof value === 'number' && Number.isFinite(value) && Math.abs(value) < 1e9 ? value : null);
const count = value => (Number.isInteger(value) && value >= 0 && value <= 1e9 ? String(value) : 'unknown');
const usd = value => (real(value) === null ? 'unknown' : `$${real(value).toFixed(2)}`);
const signedUsd = value => (real(value) === null ? 'n/a' : `${real(value) < 0 ? '-' : '+'}$${Math.abs(real(value)).toFixed(2)}`);
const bp = value => (real(value) === null ? 'n/a' : `${real(value) < 0 ? '' : '+'}${real(value).toFixed(1)} bp`);
const pct = value => (real(value) === null ? 'n/a' : `${Math.round(real(value))}%`);
const versionOf = value => (Number.isInteger(value) && value > 0 && value < 1000 ? value : null);
const programOf = value => (typeof value === 'string' && PROGRAM_ID.test(value) ? value.slice(4) : null);
const bandOf = value => (BANDS.includes(value) ? value : 'unknown');
//: Release 1019f (league/ops/daily_report.py `day_entries`): why an event buy never reached the venue, and the
//: constraint that bound an auction, as the House names them (league/ops/evl_health.py UNSENT and BOUND), in words.
//: A name not here is not echoed.
export const ENTRY_WORDS = {
  order_line: 'order line', cash: 'cash', budget: 'loss budget', name_wall: 'name wall', invested: 'invested cap',
  room: 'room', price: 'share price', min_order: 'minimum order', gateway: 'gateway', sale: 'same-cross sale',
  busy: 'working order', blocked: 'a gate', unreadable: 'unread figure', other: 'other',
};
const AUCTIONS = { open: 'open', close: 'close' };
//: Release 1019h (league/ops/daily_report.py `supply_line`): the cap most often recorded on a row's Probe+ buys under
//: Done's size bar (league/events/bands.py BINDINGS), in words; "none" when no cap was recorded.
const SUPPLY_BOUND = {
  cash: 'cash', budget: 'loss budget', invested: 'invested cap', name_wall: 'name wall', whole_shares: 'whole shares',
  gateway: 'gateway', venue: 'venue', none: 'no cap recorded',
};
const reasons = value => Object.entries(plain(value))
  .filter(([name, n]) => Object.hasOwn(ENTRY_WORDS, name) && Number.isInteger(n) && n > 0)
  .map(([name, n]) => `${ENTRY_WORDS[name]} ${n}`);

/**
 * `text` as lines of at most `width` characters: as it is when it fits, else cut at the last space that fits (a word
 * longer than a line is cut where the line ends), each line after the first indented by `indent`.
 */
function wrap(text, width = REPORT_WIDTH, indent = '  ') {
  const out = [];
  let rest = String(text);
  while (rest.length > width) {
    let cut = rest.lastIndexOf(' ', width);
    if (cut <= indent.length) cut = width;
    out.push(rest.slice(0, cut).trimEnd());
    rest = indent + rest.slice(cut).trimStart();
  }
  out.push(rest);
  return out;
}

/** `head` then `items` joined by `sep`, a new line (indented by `indent`) wherever the next item would not fit: an item is
 * never cut across lines unless it alone is longer than a line. */
function pack(head, items, sep = '; ', width = REPORT_WIDTH, indent = '  ') {
  const out = [];
  let line = head;
  items.forEach((item, i) => {
    const piece = `${item}${i < items.length - 1 ? sep.trimEnd() : ''}`;
    const next = line.endsWith(' ') || line === indent ? `${line}${piece}` : `${line} ${piece}`;
    if (next.length <= width || line === indent) {
      line = next;
    } else {
      out.push(line);
      line = `${indent}${piece}`;
    }
  });
  out.push(line);
  return out.flatMap(text => wrap(text, width, indent));
}

/** The dedupe key of a daily report, whatever id the House sent: `report:<day>` (the Gate keeps it 48 hours), or null. */
export function reportKey(facts = {}) {
  return typeof facts?.day === 'string' && DAY.test(facts.day) ? `report:${facts.day}` : null;
}

/**
 * The daily report's `{ subject, lines }` (league/ops/daily_report.py `facts`), or null when the notice is not one: no
 * New York day. Account-shown profit first, Net after costs beside it (to date as far as the House's meters cover it:
 * "since <day>, partly measured" when they start after the first fill or a day's reading falls short); the MEASURED
 * metered compute of the UTC day of the same date against its cap ("OVER the cap" when above it), the cap and its lines
 * labelled the allowance; then the events, verdicts, real
 * fills and shadow intents of the day, each real-money program's band, settled n, P&L by band and evidence, the
 * records, the same-risk buy-and-hold, the expected false passes and the alarms open.
 */
export function composeReport(facts = {}) {
  const day = reportKey(facts) ? facts.day : null;
  if (!day) return null;
  const profit = plain(facts.profit), today = plain(profit.day), toDate = plain(profit.to_date);
  const costs = plain(facts.costs), allowance = plain(costs.allowance), yesterday = plain(costs.yesterday);
  const events = plain(facts.events), verdicts = plain(facts.verdicts), fills = plain(facts.fills);
  const records = plain(facts.records), hold = plain(facts.buy_hold);
  const alarms = list(facts.alarms).filter(cause => typeof cause === 'string' && Object.hasOwn(STALL_CAUSES, cause));
  const traded = real(toDate.shown_usd) !== null;
  const known = real(costs.spent_usd), least = real(costs.at_least_usd);
  const spent = known !== null ? known : least;   // a meter with no reading: what the others show, at least
  const over = costs.over === true;
  // COSTS TO DATE as far as the House's meters cover them (league/ops/metered.py `since`): from `costs_from` (a ledger
  // begun after the first fill measures from its own first day), `partial` when that or a day's reading falls short.
  const partly = traded && toDate.partial === true && real(toDate.metered_usd) !== null;
  const costsFrom = typeof toDate.costs_from === 'string' && DAY.test(toDate.costs_from) ? toDate.costs_from : null;
  const unread = list(toDate.missing).filter(item => typeof item === 'string' && DAY.test(item)).slice(0, 5);
  const subject = `LTCM daily ${day}: `
    + (traded ? `shown ${signedUsd(toDate.shown_usd)}, net ${signedUsd(toDate.net_usd)}${partly ? ' (costs partial)' : ''}`
      : `no real fills yet; costs ${usd(spent)}`)
    + (over ? ' (over the cap)' : '') + (alarms.length ? `; ${alarms.length} alarm${alarms.length === 1 ? '' : 's'}` : '');
  const out = [];
  const add = (text, indent = '  ') => out.push(...wrap(text, REPORT_WIDTH, indent));
  add(`The event lane, ${day} (New York day).`);
  out.push('');
  add('Profit, real money (account-shown | net of costs):');
  add(` today:   ${signedUsd(today.shown_usd)} | ${signedUsd(today.net_usd)}`);
  if (traded) {
    add(` to date: ${signedUsd(toDate.shown_usd)} | ${signedUsd(toDate.net_usd)}`);
    add(`  since ${typeof toDate.since === 'string' && DAY.test(toDate.since) ? toDate.since : 'unknown'}, `
      + `${count(toDate.events)} settled; costs ${usd(toDate.metered_usd)}`
      + (partly ? `${costsFrom ? ` since ${costsFrom}` : ''}, partly measured` : ''), '   ');
    if (partly && unread.length) add(`  a meter unread on ${unread.join(', ')}`, '   ');
  } else {
    add(' to date: n/a until real fills');
  }
  out.push('');
  // The costs are THE UTC DAY of the report's date (budget rule 3's day, on which every line is held and the cap
  // breach is judged; it ends at 20:00 ET, 19:00 ET in winter, so it is whole by the report's time), HH:MM in UTC.
  const read = typeof costs.from === 'string' && HHMM.test(costs.from) && typeof costs.to === 'string' && HHMM.test(costs.to);
  const span = costs.whole === true ? 'measured the whole day' : read ? `measured ${costs.from}-${costs.to} UTC`
    : 'no meter read yet';
  add(`Costs, UTC day, ${span}: ${usd(spent)}${known === null ? ' at least' : ''}`);
  add(over ? ` OVER the day's cap of ${usd(costs.cap_usd)}` : ` under the day's cap of ${usd(costs.cap_usd)}`);
  add(` Sail ${usd(costs.sail_usd)}, Claude ${usd(costs.claude_usd)} (verdicts ${usd(costs.verdicts_usd)})`);
  add(` Cloudflare ${usd(costs.cloudflare_usd)}, data ${usd(costs.data_usd)}`
    + (real(costs.openai_usd) ? `, OpenAI ${usd(costs.openai_usd)}` : ''));
  add(` Allowance${allowance.source === 'floor' ? ' (the floor)' : ''}: cap ${usd(allowance.cap_usd)}, fixed ${usd(allowance.fixed_usd)}, `
    + `lane ${usd(allowance.lane_usd)}, research ${usd(allowance.research_usd)}`, '   ');
  if (typeof yesterday.day === 'string' && DAY.test(yesterday.day)) {
    const whole = real(yesterday.spent_usd), some = real(yesterday.at_least_usd);
    const was = whole !== null ? whole : some;
    add(` Yesterday: ${usd(was)} of ${usd(yesterday.cap_usd)}`
      + (yesterday.whole === true ? '' : ' (partly measured)') + (yesterday.over === true ? ', OVER the cap' : ''));
  }
  out.push('');
  add(`Events: 8-K 2.02 ${count(events['8k_202'])}, other 8-K ${count(events['8k_other'])}, Form 4 `
    + `${count(events.form4)}, news ${count(events.news)}; ${count(events.failed)} failed`);
  add(`Verdicts: ${count(verdicts.ok)} ok, ${count(verdicts.unparsed)} unparsed, ${count(verdicts.refused)} refused, `
    + `${usd(verdicts.usd)}`);
  add(`Real fills: ${count(fills.buys)} buys, ${count(fills.sells)} sells, fees ${usd(fills.fees_usd)}`);
  const gap = plain(fills.gap);
  if (Number.isInteger(gap.entry_n) && Number.isInteger(gap.exit_n) && gap.entry_n + gap.exit_n > 0) {
    add(` Fill gap vs the auction (worse +): entry ${bp(gap.entry_mean_bp)} (${count(gap.entry_n)}), exit `
      + `${bp(gap.exit_mean_bp)} (${count(gap.exit_n)})`, '   ');
  }
  // THE DAY'S REAL BUYS (release 1019f; A80 (2): the venue's cancels at once count as a fill gap): planned and
  // filled, the venue's cancels and A80's re-sends, the never-sent by reason, sent and not filled, the decisions' room
  // cut; per auction its filled of planned and the constraint that bound it. Then, once a Probe buy exists, THE
  // BREAK-EVEN EDGE of Done's compute clause: metered compute per session over the Probe dollars bought per session.
  const entries = plain(facts.entries), totals = plain(entries.totals);
  if (Number.isInteger(totals.planned) && totals.planned > 0) {
    add(`Real buys ${count(totals.filled)}/${count(totals.planned)} filled; venue cancels ${count(totals.venue_cancels)} `
      + `(re-sent ${count(totals.resent)}, filled ${count(totals.resent_filled)})`, '   ');
    const unsent = reasons(totals.never);
    add(` never sent ${count(totals.never_sent)}${unsent.length ? ` (${unsent.join(', ')})` : ''}; not filled `
      + `${count(totals.unfilled)}; room cut ${count(totals.room_cut)}`, '   ');
    const per = list(entries.auctions).slice(0, 2)
      .filter(row => row && Object.hasOwn(AUCTIONS, row.at) && Number.isInteger(row.planned) && row.planned > 0)
      .map(row => `${AUCTIONS[row.at]} ${count(row.filled)}/${count(row.planned)} bound `
        + `${Object.hasOwn(ENTRY_WORDS, row.bound) ? ENTRY_WORDS[row.bound] : 'none'}`);
    if (per.length) out.push(...pack(' By auction:', per));
  } else if (Number.isInteger(totals.planned)) {
    add('Real buys: none planned today');
  }
  const even = plain(facts.break_even);
  if (typeof even.since === 'string' && DAY.test(even.since)) {
    add(real(even.edge_bp) === null ? 'Break-even edge: n/a (compute not measured)'
      : `Break-even edge ${bp(even.edge_bp)} (${usd(even.compute_per_session)} / ${usd(even.probe_per_session)} `
        + `Probe, a session)${even.partial === true ? ', costs partial' : ''}`, '   ');
  }
  const byId = new Map();
  let skipped = 0;
  for (const row of list(facts.intents)) {
    const id = programOf(row?.id), version = versionOf(row?.version);
    if (!id || !version || !Number.isInteger(row.n) || row.n < 0) continue;
    if (!byId.has(id)) byId.set(id, []);
    byId.get(id).push(`v${version}:${row.n}`);
    if (Number.isInteger(row.skipped) && row.skipped > 0) skipped += row.skipped;
  }
  const intents = [...byId.entries()].map(([id, parts]) => `${id} ${parts.join(' ')}`);
  out.push(...pack('Shadow intents today:', [...(intents.length ? intents : ['none']), ...(skipped ? [`${skipped} skipped`] : [])]));
  out.push('');
  const programs = list(facts.programs).slice(0, REPORT_PROGRAMS)
    .filter(row => row && typeof row === 'object' && programOf(row.id) && versionOf(row.version));
  if (programs.length) {
    add('Real-money programs: band; settled shadow TRADABLE | real; shown | net; next look');
    for (const row of programs) {
      const shown = real(row.shown_usd) === null ? 'no real event' : `${signedUsd(row.shown_usd)} | ${signedUsd(row.net_usd)}`;
      add(` ${programOf(row.id)} v${versionOf(row.version)} ${bandOf(row.band)}: ${count(row.shadow_tradable)} | `
        + `${count(row.real)}; ${shown}`, '   ');
      const look = Number.isInteger(row.next_look) ? `look ${row.next_look} in ${count(row.events_to_go)}` : 'every look written';
      add(`  ${look}; market ${pct(row.market_share_pct)}, bench ${bp(row.bench_mean_bp)}`
        + (real(row.buy_hold_usd) === null ? '' : `; b&h ${signedUsd(row.buy_hold_usd)}`), '   ');
      const bands = list(row.by_band).filter(b => b && BANDS.includes(b.band) && Number.isInteger(b.n) && b.n > 0);
      if (bands.length > 1) {
        for (const b of bands) add(`  ${b.band} ${b.n}: ${signedUsd(b.shown_usd)} | ${signedUsd(b.net_usd)}`, '   ');
      }
    }
    out.push('');
  }
  // THE DONE LINE (the goal V2, docs/goals/DONE-RULE-EVL-2.md; league/ops/daily_report.py `done_line`): the settled
  // real-money events at Probe size or above toward 300 by program, the next checkpoint and the 95% issuer-block lower
  // bound of the per-event after-cost return; figures and the programs' own ids only.
  const done = plain(facts.done);
  if (Object.keys(done).length) {
    const toward = Number.isInteger(done.toward) ? done.toward : 300;
    if (Number.isInteger(done.counted)) {
      add(`Done, Probe+ real events: ${count(done.counted)} of ${count(toward)}, next at ${count(done.next_checkpoint)}`);
      add(` bound ${bp(done.lower_bp)} (net of bench ${bp(done.lower_a_bp)}); learning ${count(done.learning)} beside`, '   ');
    } else {
      add('Done, Probe+ real events: not read yet');
    }
    const parts = [];
    for (const row of list(done.by_program)) {
      const id = programOf(row?.id), version = versionOf(row?.version);
      if (id && version && Number.isInteger(row.n) && row.n > 0) parts.push(`${id} ${row.n}`);
    }
    if (done.holds === true) parts.push('DONE at a checkpoint');
    if (done.pivot === true) parts.push('PIVOT: retire the lane');
    if (done.stop === true) parts.push('$800 SPENT: stop all spend');
    if (parts.length) out.push(...pack('', parts, '; ', REPORT_WIDTH, '  ').map(line => ` ${line.trimStart()}`));
  }
  // THE DONE SUPPLY LINE (release 1019h, SUP-4, the captain's A97; league/ops/daily_report.py `supply_line`; report
  // only): each Probe+ row's counted events, its MEASURED real picks a session over the last 5 sessions, its Probe+
  // buys under Done's size bar and the cap most often recorded on them, and the session its projection reaches Done's 50
  // at the STATED season multipliers (never measured: the line says so); a FLAG when fewer than 3 rows reach 50 by the
  // checkpoint Done is first read at. Figures and the programs' own ids only.
  const supply = plain(facts.supply);
  if (Object.keys(supply).length) {
    const rows = list(supply.rows).filter(row => row && typeof row === 'object' && programOf(row.id) && versionOf(row.version))
      .slice(0, REPORT_PROGRAMS);
    if (!rows.length) {
      add('Done supply: no Probe+ row yet (Done needs 3 x 50)');
    } else {
      const parts = rows.map(row => {
        const picks = real(row.picks_per_session) === null ? 'n/a' : real(row.picks_per_session).toFixed(1);
        const to = row.to_50 === 0 ? '50 reached' : Number.isInteger(row.to_50) && row.to_50 > 0
          ? `50 in ${row.to_50}${typeof row.on_day === 'string' && DAY.test(row.on_day) ? ` (${row.on_day})` : ''}`
          : '50 not in reach';
        const under = Number.isInteger(row.under_size) && row.under_size > 0
          ? `, under ${row.under_size}${Object.hasOwn(SUPPLY_BOUND, row.under_bound) ? ` (${SUPPLY_BOUND[row.under_bound]})` : ''}`
          : '';
        const read = Number.isInteger(row.decisions) && row.decisions < 5 ? ` (${count(row.decisions)} read)` : '';
        return `${programOf(row.id)}${row.band === 'sized' ? ' sized' : ''} ${count(row.counted)}, ${picks}/session${read}, `
          + `${to}${under}`;
      });
      const head = supply.stated === false ? 'Done supply, Probe+:' : 'Done supply, Probe+ (seasons stated, not measured):';
      out.push(...pack(head, parts, '; ', REPORT_WIDTH, '  ')
        .map((line, i) => (i ? ` ${line.trimStart()}` : line)));
      const when = Number.isInteger(supply.checkpoint_in) ? `in ${count(supply.checkpoint_in)} sessions`
        : `not within ${count(supply.horizon)} sessions`;
      add(`${supply.flag === true ? ' FLAG: ' : ' '}${count(supply.reach)} of ${count(rows.length)} reach 50 by `
        + `${count(supply.checkpoint)} (${when})${supply.flag === true ? '; needs 3' : ''}`, '   ');
    }
  }
  add(`Records and controls: ${count(records.versions)} versions; today ${count(records.intents)}; settled `
    + `${count(records.settled)}`);
  add(`Same-risk buy-and-hold: ${real(hold.usd) === null ? (traded ? 'n/a' : 'n/a until real fills') : signedUsd(hold.usd)}`);
  add(`Expected false passes: ${real(facts.expected_false_passes) === null ? 'unknown' : real(facts.expected_false_passes).toFixed(1)} `
    + `(0.10 x ${count(facts.seatable_versions)} versions)`);
  out.push(...pack('Alarms open:', alarms.length ? alarms.map(cause => STALL_CAUSES[cause]) : ['none']));
  if (facts.lane_report === false) add('The lane\'s own report job did not run for this day.');
  out.push('', `At: ${typeof facts.at === 'string' && DATE.test(facts.at) ? facts.at : 'an unknown time'}.`);
  return { subject, lines: out };
}

/**
 * `{ subject, text }` for a trade notice posted by the floor, or null for a kind this does not
 * know. The floor sends the facts; the words are composed here so every line is tested.
 */
export function composeNotice(facts = {}) {
  const lines = [];
  let subject;
  const desk = clip(facts.desk_name, 60) || 'A desk';
  switch (facts.kind) {
    case 'trade': {
      const verb = facts.purpose === 'exit' ? 'closed' : (String(facts.side).toLowerCase().startsWith('s') || facts.side === 'ask' ? 'sold' : 'bought');
      const what = `${clip(facts.quantity, 24)} ${clip(facts.instrument, 60)}`;
      subject = `LTCM: ${desk} ${verb} ${what} at ${price(facts.price)}`;
      lines.push(
        `${desk} ${verb} ${what} at ${price(facts.price)} on ${clip(facts.venue, 20) || 'the venue'}${facts.fee ? `, fee $${clip(facts.fee, 20)}` : ''}.`,
        facts.purpose === 'exit' ? `Exit reason: ${clip(facts.exit_reason, 40) || 'the desk'}.` : null,
        '',
        'Why, in the desk\'s words:',
        clip(facts.rationale, 1500) || '(no rationale filed)',
        '',
        `Risk engine: ${clip(facts.engine, 400) || 'no record'}.`,
        `Critic: ${clip(facts.critic, 400) || 'no review'}.`,
        (facts.target_price || facts.stop_price || facts.time_stop_at)
          ? `Exit plan: target ${price(facts.target_price)}, stop ${price(facts.stop_price)}, out by ${clip(facts.time_stop_at, 30) || 'no time stop'}.`
          : 'Exit plan: none filed.',
        '',
        `Trade story: ${clip(facts.story_url, 300) || FLOOR}`,
      );
      break;
    }
    case 'settled': {
      const pnl = Number(facts.pnl);
      const signed = Number.isFinite(pnl) ? `${pnl < 0 ? '-' : '+'}$${Math.abs(pnl).toFixed(2)}` : clip(facts.pnl, 20);
      subject = `LTCM: ${desk}'s ${clip(facts.instrument, 60)} settled ${signed}`;
      lines.push(
        `${desk}'s position in ${clip(facts.instrument, 60)} settled ${clip(facts.result, 40) || 'unknown'}: ${signed} on ${clip(facts.quantity, 24)} held ${clip(facts.held_for_hours, 16)} h (entry ${price(facts.entry_price)}, exit ${price(facts.exit_price)}).`,
        '',
        'What the desk said going in:',
        clip(facts.rationale, 1500) || '(no rationale filed)',
        '',
        `Desk page: ${clip(facts.story_url, 300) || FLOOR}`,
      );
      break;
    }
    case 'live_stop': {
      // A stop the House tripped on real money (Sept 26, 2026, Wave 5): the drawdown stop pauses real money, the daily
      // stop holds new real entries until tomorrow, a reconciliation or assignment stop freezes real entries.
      const stop = LIVE_STOPS.includes(facts.stop) ? facts.stop : null;
      if (!stop) return null;
      subject = stop === 'drawdown' ? 'LTCM: real money paused (drawdown)'
        : stop === 'daily' ? 'LTCM: no new real entries today (daily stop)'
          : `LTCM: real entries frozen (${stop})`;
      const equity = typeof facts.equity === 'string' && DECIMAL.test(facts.equity) ? `$${facts.equity}` : 'unknown';
      lines.push(
        clip(facts.text, 1500) || '(no reason filed)',
        '',
        `Equity: ${equity}.`,
        `At: ${clip(facts.at, 40) || 'an unknown time'}.`,
        stop === 'drawdown' ? RELEASE_DRAWDOWN : null,
      );
      break;
    }
    case 'funding': {
      // A prefund under the card line (V3-A, WP8; the budget's rule version 2, Oct 3, 2026): the budget rule
      // (league/ops/budget.py `notice_facts`) found a meter's days of research left at the rate it WANTS (`usd_day`:
      // fixed + its share of the owner's research ceiling) under `card_line_days`, and says exactly what buys
      // `topup_days` more of them at that rate. Below a short runway the rule tapers research, so the desk may be held
      // under that: `current_*` are the rate it is held to now (the fixed cost plus the day's research budget: a
      // ceiling the rule sets, not a metered spend; the same as the wanted rate until the taper starts). The mail says
      // both, each named, and words neither as a spend. Both runways are days until the meter's RESERVE, not until it
      // is empty (the House sends no reserve figure), so each is said as days above the reserve. With no
      // `current_usd_day` (an older House, or a balance the rule could not read for research) it claims no current
      // rate. At most once per meter per ISO week (its notice id, which the gateway also remembers for eight days).
      // `test: true` is a drill.
      // THE AMOUNT UNDER EITHER RULE'S NAMES. The House and this gateway are separate deploys, so the facts may be the
      // other rule version's: rule version 2 sends `topup_usd`/`topup_days` (what buys more days at the ceiling) and,
      // the same values, version 1's `restore_usd`/`restore_days`; a House still on version 1 sends only those (what
      // restores its runway at the floor plus the profit share). The amount is read from the names that came and the
      // mail keeps that rule's words, so a House and a gateway on different versions never mail "add unknown".
      if (!Object.hasOwn(FUNDING_METERS, facts.meter)) return null;
      const meter = FUNDING_METERS[facts.meter];
      const drill = facts.test === true;
      const topupUsd = facts.topup_usd, topupDays = facts.topup_days, restoreUsd = facts.restore_usd, restoreDays = facts.restore_days;
      const versionOne = (topupUsd ?? null) === null && (restoreUsd ?? null) !== null;
      const amount = dollars(versionOne ? restoreUsd : topupUsd);
      const fixed = dollars(facts.fixed_usd_day);
      const current = decimal(facts.current_usd_day) !== null;
      // A runway the House sent as zero: the meter sustains nothing at that rate.
      const zero = value => decimal(value) !== null && Number(decimal(value)) <= 0;
      // What happens with no card is ONE sentence, worded from the runway at the rate the desk is held to now when that
      // was sent, and from the runway at the wanted rate only when it was not: the mail never says that the meter lasts
      // some days and that it has none left.
      const lasts = current && decimal(facts.current_runway_days) !== null ? dayCount(facts.current_runway_days) : null;
      const spent = lasts !== null ? zero(facts.current_runway_days) : zero(facts.runway_days);
      // "Nothing stops" is said only when the figures sent show it: research above zero (the throttle still has something
      // to cut), the runway at that rate at or over the card line, AND a runway left at the wanted rate. Research already
      // at 0.00 leaves the fixed cost running the meter to its reserve (at Sail's the desks stop: `floor_stopped` above),
      // so the mail then says how long it lasts and promises nothing; with no current rate, or no runway at it, it says
      // that was not sent.
      const idle = current && zero(facts.current_research_usd_day);
      const holds = lasts !== null && !idle && !zero(facts.runway_days) && decimal(facts.current_research_usd_day) !== null
        && decimal(facts.card_line_days) !== null && Number(lasts) >= Number(decimal(facts.card_line_days));
      subject = `${drill ? 'LTCM [drill]' : 'LTCM'}: ${meter} runway ${dayCount(facts.runway_days)} days at the rate the budget wants; add ${amount} by ${dateOf(facts.card_date)}`;
      lines.push(
        drill ? 'THIS IS A DRILL: a synthetic cliff tests that this notice reaches you. Its figures are the drill\'s, not the desk\'s. Nothing needs doing.' : null,
        `${meter} holds ${dollars(facts.balance_usd)}.`,
        current
          ? `The desk is held to ${dollars(facts.current_usd_day)} a day on it now (fixed ${fixed}, research up to ${dollars(facts.current_research_usd_day)}); ${lasts === null ? 'the House sent no runway at that rate' : `at that rate it lasts ${lasts} days above its reserve`}.`
          : 'What the desk is held to on it now was not sent: the figures below are at the rate the budget rule wants, not a spend the desk is making.',
        `The budget rule wants ${dollars(facts.usd_day)} a day for it (fixed ${fixed}, research ${dollars(facts.research_usd_day)}: ${versionOne ? 'the research floor plus what profit earned' : 'its share of the research ceiling'}); at that rate it lasts ${dayCount(facts.runway_days)} days above its reserve, to about ${dateOf(facts.runs_out_on)}. That is the runway under the ${dayCount(facts.card_line_days)}-day card line.`,
        versionOne
          ? `Adding ${amount} restores ${dayCount(restoreDays)} days of runway at the rate the rule wants. Add it by ${dateOf(facts.card_date)}.`
          : `Adding ${amount} buys ${dayCount(topupDays)} more days at the rate the rule wants. Add it by ${dateOf(facts.card_date)}.`,
        spent
          ? `${meter} has no runway left above its reserve: research on it stays throttled until it is funded.`
          : holds
            ? `Nothing stops if no card is added: research stays throttled to what ${meter} sustains.`
            : lasts !== null
              ? `If no card is added, ${meter} lasts ${lasts} days above its reserve at the rate the desk is held to now: research on it ${idle ? `is already at ${dollars(facts.current_research_usd_day)}, so there is nothing left to throttle` : versionOne ? 'stays throttled' : 'tapers as the balance falls'}.`
              : `If no card is added, research on ${meter} stays throttled; how long ${meter} lasts at the rate the desk is held to now was not sent.`,
        'The budget rule never raises a cap or moves money.',
        `At: ${clip(facts.at, 40) || 'an unknown time'}.`,
      );
      break;
    }
    case 'stall': {
      // A stall (the owner's goal of Oct 7, 2026, item 6): the House's `stall` job (league/ops/stall.py `notice_facts`)
      // found the floor not improving itself and lists every cause standing in one mail. The subject is this file's
      // words for the causes: "needs you" and the causes with an owner step when there is one, else "stalled" and every
      // cause. The body opens with the owner steps (or says nothing needs the owner), then each cause: its words, the
      // House's sentence for it, its figures (each name a lower-case word, each value a decimal, a date or time, yes or
      // no or a short token, else unknown), how long, what the House is doing about it, and its owner step. The router
      // keys the dedupe on the owner causes (`stallKey`), whatever id the House sends.
      const entries = stallEntries(facts);
      if (!entries) return null;
      const owner = entries.filter(item => item.step);
      const named = list => {
        const words = list.map(item => STALL_CAUSES[item.cause]);
        return words.length > 3 ? `${words.slice(0, 3).join(', ')} and ${words.length - 3} more` : words.join(', ');
      };
      // Release 1019f: an INFO notice the House sends while an owner cause it told inside 12 hours still stands names
      // that cause (`waiting_owner`, ids only, worded here; never part of the key): nothing NEW needs the owner.
      const listed = new Set(entries.map(item => item.cause));
      const waiting = owner.length ? [] : [...new Set(Array.isArray(facts.waiting_owner) ? facts.waiting_owner : [])]
        .filter(cause => typeof cause === 'string' && Object.hasOwn(STALL_CAUSES, cause) && !listed.has(cause))
        .slice(0, Object.keys(STALL_CAUSES).length);
      subject = owner.length ? `LTCM: needs you: ${named(owner)}` : `LTCM: stalled: ${named(entries)}`;
      lines.push(...(owner.length
        ? ['Only you can do this; the House keeps working around it meanwhile:', ...owner.map(item => `- ${item.step.replace(/\.$/, '')}.`)]
        : waiting.length
          ? ['Nothing new here needs you: the House keeps working around it. Still waiting on you, as mailed within the '
            + `last 12 hours: ${waiting.map(cause => STALL_CAUSES[cause]).join('; ')}.`]
          : ['Nothing here needs you: the House keeps working around it, and says so again in 24 hours if it still stands.']), '');
      for (const { entry, cause, step } of entries) {
        const numbers = entry.numbers && typeof entry.numbers === 'object' && !Array.isArray(entry.numbers)
          ? Object.entries(entry.numbers).filter(([name]) => FIGURE_NAME.test(name)).slice(0, STALL_NUMBERS) : [];
        const hours = decimal(entry.hours);
        const since = typeof entry.since === 'string' && DATE.test(entry.since) ? entry.since : null;
        lines.push(
          `Stalled: ${STALL_CAUSES[cause]}.`,
          sentence(entry.what, 400) || null,
          ...(numbers.length ? ['The numbers:', ...numbers.map(([name, value]) => `- ${name}: ${figure(value)}`)] : []),
          hours === null ? 'How long: unknown.' : `How long: ${Number(hours)} hours${since ? `, since ${since}` : ''}.`,
          `What the House is doing: ${sentence(entry.doing, 700) || 'it did not say.'}`,
          step ? `Only you can do this: ${step.replace(/\.$/, '')}.` : null,
          '',
        );
      }
      lines.push(`At: ${clip(facts.at, 40) || 'an unknown time'}.`);
      break;
    }
    case 'report': {
      // THE DAILY ONE-SCREEN REPORT (release 1019c; `composeReport`): figures only, no line over REPORT_WIDTH.
      const report = composeReport(facts);
      if (!report) return null;
      subject = report.subject;
      lines.push(...report.lines);
      break;
    }
    case 'test':
      subject = 'LTCM: trade notices are switched on';
      lines.push(
        'This is the notice you will get when a desk completes a trade on real money: what it did, why in its own words, the risk engine and critic verdicts, and the exit plan. A second kind arrives when a position settles, with the profit or loss.',
      );
      break;
    default:
      return null;
  }
  lines.push('', FLOOR, CONSOLE);
  return { subject, text: lines.filter(line => line !== undefined && line !== null).join('\n') + '\n' };
}

const ASCII = /^[\x20-\x7e]*$/;

/** RFC 2047 encoding, used only when a header actually needs it. */
export const encodeHeader = value =>
  (ASCII.test(value) ? value : `=?UTF-8?B?${Buffer.from(value, 'utf8').toString('base64')}?=`);

/**
 * A minimal RFC 5322 message. The body is base64 so no line length, no 8-bit byte and no line in
 * the text can break the envelope.
 */
export function mime({ from = FROM, to = TO, subject, text, at = Date.now(), id }) {
  const body = Buffer.from(text, 'utf8').toString('base64').match(/.{1,76}/g) || [''];
  const messageId = id || `ltcm-${at}-${Math.random().toString(36).slice(2, 10)}`;
  const domain = from.split('@')[1] || 'blakewoods.us';
  return [
    `From: Long-Term Capital Management <${from}>`,
    `To: <${to}>`,
    `Subject: ${encodeHeader(subject)}`,
    `Message-ID: <${messageId}@${domain}>`,
    `Date: ${new Date(at).toUTCString().replace(/GMT$/, '+0000')}`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset="utf-8"',
    'Content-Transfer-Encoding: base64',
    '',
    ...body,
    '',
  ].join('\r\n');
}
