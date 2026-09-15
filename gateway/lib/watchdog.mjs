// The watchdog: the part of this system that is supposed to make a human unnecessary.
//
// Every five minutes it reads three things -- the floor's published checkpoint, the Sail credit
// balance, and the state of the box the desks run on -- and then does the smallest thing that
// helps. A paused box with credit behind it is resumed and restarted, so a top-up alone brings
// the floor back with no human step. A box that has gone quiet is restarted, at most once every
// thirty minutes, so a box that cannot come back is left stopped rather than thrashed.
//
// It sends mail only when it has run out of things it can do by itself, and then at most once
// every six hours per kind. The one exception is the evening digest, which is the owner reading
// the floor rather than the floor asking for help.

import { iso } from './http.mjs';
import { compose, FROM, TO } from './email.mjs';
import {
  usageSummary, boxStatus, resumeBox, execRestart, boundedText, STOPPED, RESUMABLE,
} from './sail.mjs';

export const DEFAULT_CHECKPOINT = 'https://blakewoods.us/api/capital/checkpoint';
export const DEFAULT_COMMAND = '/workspace/restart.sh';
export const STALE_SECONDS = 900;
export const COOLDOWN_SECONDS = 1800;
export const ALERT_EVERY_SECONDS = 6 * 3600;
export const LOW_BALANCE_USD = 60;
export const CRITICAL_BALANCE_USD = 20;
export const DIGEST_UTC_HOUR = 21;
/**
 * Sail's `range` accepts `1h`, `6h`, `24h`, `7d`, `30d` and `period`, and silently falls back to
 * its 30-day default for anything else -- so "a day" has to be spelled `24h` or the digest would
 * quietly report a month of spend.
 */
export const USAGE_RANGE = '24h';

const positive = (value, fallback) => {
  const parsed = Number(String(value ?? '').trim());
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};
const amount = value => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/** The floor's own checkpoint: when it was published, and the numbers the digest reports. */
export async function readCheckpoint({ url, fetcher }) {
  let reached = false;
  try {
    const response = await fetcher(url, {
      redirect: 'manual',
      signal: AbortSignal.timeout(20000),
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      response.body?.cancel();
      return { error: 'checkpoint_unreachable', detail: `http_${response.status}` };
    }
    reached = true;
    const body = JSON.parse(await boundedText(response, 2 * 1024 * 1024));
    const stamp = Date.parse(body.published_at);
    if (!Number.isFinite(stamp)) return { error: 'checkpoint_unreadable', detail: 'no_published_at' };
    return {
      published_at: body.published_at,
      at: stamp,
      equity_usd: amount(body.floor?.equity),
      daily_pnl_usd: amount(body.floor?.daily_pnl),
    };
  } catch (error) {
    return {
      error: reached ? 'checkpoint_unreadable' : 'checkpoint_unreachable',
      detail: error?.name === 'SyntaxError' ? 'invalid_json' : 'transport',
    };
  }
}

/**
 * One pass. Always records what it saw; returns `{ action, alerts, ... }`.
 *
 * Actions: `ok`, `checkpoint_unreachable`, `checkpoint_unreadable`, `stale_no_sailbox`,
 * `cooldown`, `resumed`, `resume_failed`, `restarted`, `restart_failed`,
 * `stopped_low_balance`, `box_unrecoverable`.
 */
export async function runWatchdog({ gate, env = {}, fetcher = fetch, mailer = null, now = Date.now() }) {
  const at = iso(now);
  const apiKey = env.SAIL_API_KEY;
  const boxId = String(env.SAILBOX_ID || '').trim();
  const staleSeconds = positive(env.CHECKPOINT_STALE_SECONDS, STALE_SECONDS);
  const cooldown = positive(env.RESTART_COOLDOWN_SECONDS, COOLDOWN_SECONDS) * 1000;
  const lowBalance = positive(env.LOW_BALANCE_USD, LOW_BALANCE_USD);
  const criticalBalance = positive(env.CRITICAL_BALANCE_USD, CRITICAL_BALANCE_USD);
  const alertEvery = positive(env.ALERT_EVERY_SECONDS, ALERT_EVERY_SECONDS) * 1000;

  // ---- look ------------------------------------------------------------------------------------
  const checkpoint = await readCheckpoint({ url: env.CHECKPOINT_URL || DEFAULT_CHECKPOINT, fetcher });
  const age = checkpoint.error ? null : Math.round((now - checkpoint.at) / 1000);
  const stale = age !== null && age > staleSeconds;

  const usage = apiKey ? await usageSummary({ apiKey, fetcher, range: env.SAIL_USAGE_RANGE || USAGE_RANGE }) : null;
  const box = apiKey && boxId ? await boxStatus({ apiKey, boxId, fetcher }) : null;
  const balance = usage && !usage.error ? usage.balance_usd : null;
  const status = box && !box.error ? box.status : null;

  gate.recordSail({
    checked_at: at,
    balance_usd: balance,
    spend_usd: usage && !usage.error ? usage.spend_usd : null,
    range: usage && !usage.error ? usage.range : null,
    box_status: status ?? (box?.error ? `unreachable:${box.error}` : null),
    ...(usage?.error ? { balance_error: usage.error } : { balance_error: null }),
  });

  // ---- act -------------------------------------------------------------------------------------
  const previousRestart = Date.parse(gate.watchdog().last_restart_at || '');
  const cooling = Number.isFinite(previousRestart) && now - previousRestart < cooldown;
  const stopped = status !== null && STOPPED.includes(status);
  const record = {};
  let action = 'ok';

  if (checkpoint.error) {
    action = checkpoint.error;
  } else if (!stale && !stopped) {
    action = 'ok';
  } else if (!apiKey || !boxId) {
    action = 'stale_no_sailbox';
  } else if (stopped && !RESUMABLE.includes(status)) {
    action = 'box_unrecoverable';
  } else if (stopped && balance !== null && balance <= lowBalance) {
    // Resuming a box on the last of the credit only spends it faster and stops mid-session.
    action = 'stopped_low_balance';
  } else if (cooling) {
    action = 'cooldown';
  } else {
    // One key per cooldown window: a retry inside the window is the same recovery, not another.
    const key = `ltcm-recover:${boxId}:${Math.floor(now / cooldown)}`;
    record.last_restart_at = at; // the attempt itself opens the cooldown, confirmed or not
    if (stopped) {
      const resumed = await resumeBox({ apiKey, boxId, fetcher, idempotencyKey: `resume:${key}` });
      gate.recordSail({ last_resume_at: at, last_resume_state: resumed.resume_state ?? `error:${resumed.error}` });
      if (!resumed.ready) {
        action = 'resume_failed';
        record.detail = resumed.error || resumed.resume_state || 'unknown';
      }
    }
    if (action !== 'resume_failed') {
      const started = await execRestart({
        apiKey, boxId, fetcher, idempotencyKey: `exec:${key}`,
        command: String(env.RESTART_COMMAND || DEFAULT_COMMAND),
      });
      action = started.started ? (stopped ? 'resumed' : 'restarted') : 'restart_failed';
      if (started.detail) record.detail = started.detail;
    }
  }

  gate.recordWatchdog({
    last_check_at: at,
    last_action: action,
    last_action_at: at,
    published_at: checkpoint.published_at ?? null,
    age_seconds: age,
    ...record,
  });

  // ---- tell, only when telling is the last resort -----------------------------------------------
  const today = gate.status(now).today;
  const facts = {
    balance_usd: balance,
    spend_usd: usage && !usage.error ? usage.spend_usd : null,
    range: usage && !usage.error ? usage.range : null,
    box_status: status,
    published_at: checkpoint.published_at ?? null,
    age_seconds: age,
    equity_usd: checkpoint.equity_usd ?? null,
    daily_pnl_usd: checkpoint.daily_pnl_usd ?? null,
    orders: today.orders,
    notional_usd: Number(today.notional_usd),
    kill_switch: gate.killSwitch(),
    max_day_orders: gate.caps.maxDayOrders,
    max_day_usd: Number(gate.status(now).caps.max_day_usd),
    detail: record.detail ?? checkpoint.detail ?? null,
  };

  const sent = [];
  const send = async (kind, extra = {}) => {
    if (!mailer || !gate.alertDue(kind, now, alertEvery)) return;
    const message = compose(kind, { ...facts, ...extra });
    if (!message) return;
    try {
      await mailer({ from: env.ALERT_FROM || FROM, to: env.ALERT_TO || TO, ...message, at: now });
      gate.recordAlert(kind, now);
      sent.push(kind);
    } catch (error) {
      // A mail failure must never take the pass down: the floor is more important than the mail.
      gate.recordWatchdog({ last_mail_error: error?.name || 'send_failed', last_mail_error_at: at });
    }
  };

  if (balance !== null && balance < criticalBalance) await send('sail_balance_critical', { threshold_usd: criticalBalance });
  else if (balance !== null && balance < lowBalance) await send('sail_balance_low', { threshold_usd: lowBalance });

  const restartTried = Number.isFinite(Date.parse(record.last_restart_at || '')) || Number.isFinite(previousRestart);
  if (stopped || (stale && restartTried)) await send('box_not_running');
  if (facts.kill_switch) await send('kill_switch_engaged');
  if (gate.capsExhausted(now)) await send('caps_exhausted');
  if (new Date(now).getUTCHours() === DIGEST_UTC_HOUR) await send('daily_digest');

  return { action, at, age_seconds: age, box_status: status, balance_usd: balance, alerts: sent, ...record };
}
