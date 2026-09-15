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
const signed = value => (Number.isFinite(value) ? `${value < 0 ? '-' : '+'}$${Math.abs(value).toFixed(2)}` : 'unknown');
const number = value => (Number.isFinite(value) ? String(value) : 'unknown');

/** `{ subject, text }` for one alert. `facts` is whatever the watchdog pass learned. */
export function compose(kind, facts = {}) {
  const lines = [];
  let subject;
  switch (kind) {
    case 'sail_balance_low':
      subject = `LTCM: Sail balance ${money(facts.balance_usd)} — top up to keep the desks working`;
      lines.push(
        `The Sail credit balance is ${money(facts.balance_usd)}, under the ${money(facts.threshold_usd)} floor.`,
        'The desks keep running until it reaches zero, then the box stops and the floor goes quiet.',
        'Adding credit is the only step: the gateway resumes the box and restarts the desks on its own.',
      );
      break;
    case 'sail_balance_critical':
      subject = `LTCM: Sail balance ${money(facts.balance_usd)} — top up to keep the desks working`;
      lines.push(
        `The Sail credit balance is ${money(facts.balance_usd)}. This is the second and last warning.`,
        'When it reaches zero the box stops mid-session and open orders are left resting at the venues.',
        'Add credit now; the gateway brings the floor back by itself once there is balance.',
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
      subject = `LTCM daily: equity ${money(facts.equity_usd)}, day P&L ${signed(facts.daily_pnl_usd)}`;
      lines.push(
        `Equity: ${money(facts.equity_usd)}.`,
        `Day P&L: ${signed(facts.daily_pnl_usd)}.`,
        `Orders through the gateway today: ${number(facts.orders)} for ${money(facts.notional_usd)}.`,
        `Sail balance: ${money(facts.balance_usd)}; spend over ${facts.range || 'the window'}: ${money(facts.spend_usd)}.`,
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
    `From: Long Term Capital Management <${from}>`,
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
