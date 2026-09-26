// The only human touch this floor is designed to need. Six things can put a message in the
// owner's inbox, each at most once every six hours, and five of them are "something is wrong and
// I could not fix it myself". The sixth is the evening digest.
//
// Composition is pure and lives here so every subject and every line of every alert is checked by
// the test suite rather than discovered in production. Nothing composed here can contain a
// credential: the facts that reach it are numbers, a box status and a short failure code.

export const ALERT_KINDS = [
  'sail_balance_low',
  'sail_balance_critical',
  'floor_stopped',
  'box_not_running',
  'kill_switch_engaged',
  'caps_exhausted',
  'daily_digest',
];

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

// What the floor may post to /v1/notify: fills, settlements, the sample, a disk warning, and a real-money stop.
export const NOTICE_KINDS = ['trade', 'settled', 'test', 'disk_low', 'live_stop'];
//: The stops the House trips on real money (Sept 26, 2026 (the options-swarm run, Wave 5)). A stop not named here is not
//: composed (a 400): a subject names only these words.
export const LIVE_STOPS = ['drawdown', 'daily', 'reconciliation', 'assignment'];
export const RELEASE_DRAWDOWN = 'Exits go on; the Gym keeps running. Release the drawdown pause on the box with python3 -m league.live --root /workspace/state --release-drawdown.';
const DECIMAL = /^-?\d{1,12}(\.\d{1,6})?$/;
const clip = (value, max) => (typeof value === 'string' ? value.slice(0, max) : '');
const price = value => (typeof value === 'string' && value ? `$${value}` : 'unknown');

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
