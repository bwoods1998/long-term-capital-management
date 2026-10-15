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
//
// A box the provider took away with its checkpoint kept (`interrupted_restorable`: Oct 14, 2026, an AWS spot
// interruption, seven hours down) is asked back with Sail's resume, once every fifteen minutes and at most 48 times, on
// a key of its own window, and never forked. After three calls that did not bring it back, or 45 minutes, the owner
// hears ONE message for the interruption: Sail's community Slack and the words to post there.

import { iso } from './http.mjs';
import { compose, FROM, TO } from './email.mjs';
import { parsePico } from './money.mjs';
import {
  usageSummary, boxStatus, resumeBox, execRestart, boundedText, STOPPED, RESUMABLE, RESTORABLE,
} from './sail.mjs';

export const DEFAULT_CHECKPOINT = 'https://blakewoods.us/api/capital/checkpoint';
export const DEFAULT_COMMAND = '/workspace/restart.sh';
export const STALE_SECONDS = 900;
export const COOLDOWN_SECONDS = 1800;
export const ALERT_EVERY_SECONDS = 6 * 3600;
export const LOW_BALANCE_USD = 60;
export const CRITICAL_BALANCE_USD = 20;
// The floor's spend policy has no daily cap: the credit above the reserve is spent as the work
// needs it, so "low" is a matter of runway, not of dollars. The owner hears at a week of runway,
// again at two days, and again when the floor has actually stopped for lack of credit.
export const RESERVE_USD = 10;
export const LOW_RUNWAY_DAYS = 7;
export const CRITICAL_RUNWAY_DAYS = 2;
export const DIGEST_UTC_HOUR = 21;
/**
 * An interrupted box (`RESTORABLE`): Sail's resume is asked at most once a `RESTORE_COOLDOWN_SECONDS` window (each call
 * bounded by the Sail client's own 45 s timeout; Oct 14 every call hung), at most `RESTORE_MAX_TRIES` times an
 * interruption (twelve hours), and the owner is mailed once, after `RESTORE_MAIL_TRIES` calls that did not bring it
 * back or `RESTORE_MAIL_MINUTES` since the watchdog first saw it, whichever comes first (at once when Sail says it can
 * never resume).
 */
export const RESTORE_COOLDOWN_SECONDS = 900;
export const RESTORE_MAX_TRIES = 48;
export const RESTORE_MAIL_TRIES = 3;
export const RESTORE_MAIL_MINUTES = 45;
//: The least time between two interruption mails, whatever the episodes (a box that flaps mails at most this often).
export const RESTORE_MAIL_FLOOR_SECONDS = 3600;
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
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/**
 * Profit since the reset, from a schema-2 checkpoint (Sept 26, 2026 (the options-swarm run, Wave 5)): the account's
 * equity less the equity it started from less the owner's net deposits since (`performance.net_flows`: deposits are
 * never profit). Exact to the picodollar, then dollars. Null when any part is missing: the publisher leaves `net_flows`
 * out until the funding activities that make it are verified, and a profit without them would count a deposit as one.
 */
export function profitSinceReset(body) {
  const equity = parsePico(body?.account?.equity ?? null);
  const start = parsePico(body?.performance?.start_equity ?? null);
  const flows = parsePico(body?.performance?.net_flows ?? null);
  if (equity === null || start === null || flows === null) return null;
  return Number((equity - start - flows) / 10000n) / 1e8;
}

/**
 * The floor's own checkpoint: when it was published, and the numbers the digest reports. Schema 2 since Sept 26, 2026
 * (`league/publish.py` `build_checkpoint`): `account.equity` is the Brokerage Account's equity, and the day's P&L and
 * the floor's own `budget.mode` are gone; profit is read since the reset (`profitSinceReset`).
 */
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
      schema_version: Number.isSafeInteger(body.schema_version) ? body.schema_version : null,
      equity_usd: amount(body.account?.equity),
      equity_stale: body.account?.stale === true,
      profit_usd: profitSinceReset(body),
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
 * `stopped_low_balance`, `box_unrecoverable`, and for an interrupted box `restored`, `restore_failed`,
 * `restore_cooldown`, `restore_exhausted` (the tries are used up) and `restore_unavailable` (Sail said it can never
 * resume).
 */
/** Seconds in a Sail usage range such as `24h`, `6h`, `7d`. Unknown spellings read as a day. */
export function rangeSeconds(range) {
  const match = /^(\d+)([hd])$/.exec(String(range || '').trim());
  if (!match) return 86400;
  const n = Number(match[1]);
  return match[2] === 'h' ? n * 3600 : n * 86400;
}

export async function runWatchdog({ gate, env = {}, fetcher = fetch, mailer = null, now = Date.now() }) {
  const at = iso(now);
  const apiKey = env.SAIL_API_KEY;
  const boxId = String(env.SAILBOX_ID || '').trim();
  const staleSeconds = positive(env.CHECKPOINT_STALE_SECONDS, STALE_SECONDS);
  const cooldown = positive(env.RESTART_COOLDOWN_SECONDS, COOLDOWN_SECONDS) * 1000;
  const lowBalance = positive(env.LOW_BALANCE_USD, LOW_BALANCE_USD);
  const criticalBalance = positive(env.CRITICAL_BALANCE_USD, CRITICAL_BALANCE_USD);
  const reserve = positive(env.RESERVE_USD, RESERVE_USD);
  const lowRunway = positive(env.LOW_RUNWAY_DAYS, LOW_RUNWAY_DAYS);
  const criticalRunway = positive(env.CRITICAL_RUNWAY_DAYS, CRITICAL_RUNWAY_DAYS);
  const alertEvery = positive(env.ALERT_EVERY_SECONDS, ALERT_EVERY_SECONDS) * 1000;
  const restoreCooldown = positive(env.RESTORE_COOLDOWN_SECONDS, RESTORE_COOLDOWN_SECONDS) * 1000;
  const restoreMaxTries = Math.floor(positive(env.RESTORE_MAX_TRIES, RESTORE_MAX_TRIES));
  const restoreMailTries = Math.floor(positive(env.RESTORE_MAIL_TRIES, RESTORE_MAIL_TRIES));
  const restoreMailMs = positive(env.RESTORE_MAIL_MINUTES, RESTORE_MAIL_MINUTES) * 60000;

  // ---- look ------------------------------------------------------------------------------------
  const checkpoint = await readCheckpoint({ url: env.CHECKPOINT_URL || DEFAULT_CHECKPOINT, fetcher });
  const age = checkpoint.error ? null : Math.round((now - checkpoint.at) / 1000);
  const stale = age !== null && age > staleSeconds;

  const usage = apiKey ? await usageSummary({ apiKey, fetcher, range: env.SAIL_USAGE_RANGE || USAGE_RANGE }) : null;
  const box = apiKey && boxId ? await boxStatus({ apiKey, boxId, fetcher }) : null;
  const balance = usage && !usage.error ? usage.balance_usd : null;
  const status = box && !box.error ? box.status : null;
  // Runway: credit above the reserve over the trailing day's spend (models and the box together,
  // as Sail bills them). Sail's 24h window is the burn; a shorter configured window is scaled.
  const spend = usage && !usage.error && Number.isFinite(usage.spend_usd) ? usage.spend_usd : null;
  const burn = spend === null ? null : Math.max(spend * (86400 / rangeSeconds(env.SAIL_USAGE_RANGE || USAGE_RANGE)), 0.5);
  const spendable = balance === null ? null : Math.max(balance - reserve, 0);
  const runwayDays = spendable === null || burn === null ? null : spendable / burn;
  const runOut = runwayDays === null ? null : iso(now + runwayDays * 86400000);
  const runway = { reserve_usd: reserve, spendable_usd: spendable, burn_usd_per_day: burn, runway_days: runwayDays, run_out_at: runOut };
  gate.recordSail(runway);

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
  const restorable = status !== null && RESTORABLE.includes(status);
  const record = {};
  let action = 'ok';
  // THE INTERRUPTION, one episode a box from the pass that first saw it to the pass that sees another status. A pass
  // that could not read the box keeps the episode as it was.
  const before = gate.watchdog().restore;
  const open = before && typeof before === 'object' && !before.ended_at && before.box_id === boxId ? before : null;
  let episode = null;
  if (restorable && boxId) {
    episode = open ? { ...open } : {
      box_id: boxId, first_seen_at: at, tries: 0, last_try_at: null, last_answer: null, mailed_at: null, unavailable: false,
    };
  } else if (open && status !== null) {
    record.restore = { ...open, ended_at: at, ended_status: status };
  }

  if (checkpoint.error) {
    action = checkpoint.error;
  } else if (!stale && !stopped) {
    action = 'ok';
  } else if (!apiKey || !boxId) {
    action = 'stale_no_sailbox';
  } else if (restorable && !(balance !== null && balance <= reserve)) {
    const lastTry = Date.parse(episode.last_try_at || '');
    if (episode.unavailable) {
      action = 'restore_unavailable';
    } else if (episode.tries >= restoreMaxTries) {
      action = 'restore_exhausted';
    } else if (Number.isFinite(lastTry) && now - lastTry < restoreCooldown) {
      action = 'restore_cooldown';
    } else {
      // Sail restores an interrupted box from its last completed checkpoint on the same id: the resume call asks for it.
      // One key a window, so a retry inside it is the same request. Never a fork, and no restart in the same pass: a
      // box that comes back warm has the House running mid-session; the stale-checkpoint path below restarts it after
      // the usual cooldown if it stays quiet (`last_restart_at` is set here for that).
      const key = `ltcm-restore:${boxId}:${Math.floor(now / restoreCooldown)}`;
      const resumed = await resumeBox({ apiKey, boxId, fetcher, idempotencyKey: `resume:${key}` });
      episode.tries += 1;
      episode.last_try_at = at;
      episode.last_answer = resumed.ready ? resumed.resume_state : String(resumed.error || resumed.resume_state || 'unknown');
      gate.recordSail({ last_resume_at: at, last_resume_state: resumed.resume_state ?? `error:${resumed.error}` });
      if (resumed.ready) {
        action = 'restored';
        record.last_restart_at = at;
      } else {
        action = 'restore_failed';
        record.detail = episode.last_answer;
        if (resumed.resume_state === 'terminal_unavailable') episode.unavailable = true;
      }
    }
  } else if (stopped && !RESUMABLE.includes(status) && !restorable) {
    action = 'box_unrecoverable';
  } else if (stopped && balance !== null && balance <= reserve) {
    // Under the reserve the floor itself would refuse every model call, so a resumed box
    // would only burn its own hourly rate. Above it the floor keeps its full research loop.
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

  if (episode) record.restore = episode;
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
    ...runway,
    balance_usd: balance,
    spend_usd: usage && !usage.error ? usage.spend_usd : null,
    range: usage && !usage.error ? usage.range : null,
    box_status: status,
    published_at: checkpoint.published_at ?? null,
    age_seconds: age,
    equity_usd: checkpoint.equity_usd ?? null,
    equity_stale: checkpoint.equity_stale === true,
    profit_usd: checkpoint.profit_usd ?? null,
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


  // "Stopped for lack of credit" is Sail's to say (Sept 26, 2026, Wave 5): the schema-2 checkpoint no longer carries the
  // floor's own `budget.mode`, so the mail goes when Sail's balance is at or under the reserve (no runway left). A stale
  // checkpoint is not read as a credit stop: at the reserve the floor keeps publishing (marks, settlements), and a
  // floor that has gone quiet is `box_not_running`'s mail below, after the restart this pass may already have sent.
  if (balance !== null && balance <= reserve) await send('floor_stopped', runway);
  else if (balance !== null && (balance < criticalBalance || (runwayDays !== null && runwayDays < criticalRunway))) await send('sail_balance_critical', { threshold_usd: criticalBalance, threshold_days: criticalRunway, ...runway });
  else if (balance !== null && (balance < lowBalance || (runwayDays !== null && runwayDays < lowRunway))) await send('sail_balance_low', { threshold_usd: lowBalance, threshold_days: lowRunway, ...runway });
  // "Not running" is a verdict, not a symptom. A stale checkpoint on the first pass gets a
  // restart and the benefit of the doubt: the loop needs a minute to publish again, and a mail
  // sent before that minute is up is a false alarm on every deploy. The mail goes out when a
  // recovery attempt failed outright, when the box is stopped and this pass could not resume
  // it, or when a restart went out on an earlier pass and the floor is still quiet.
  const recoveredNow = action === 'resumed' || action === 'restarted' || action === 'restored';
  const recoveryFailed = ['restart_failed', 'resume_failed', 'box_unrecoverable', 'stale_no_sailbox', 'stopped_low_balance'].includes(action);
  const stillQuiet = stale && cooling;
  // AN INTERRUPTED BOX the watchdog is asking back is told once, by its own message, never by the six-hourly "not
  // running" (under the reserve it is the credit's case, told as before).
  const restoring = restorable && ['restore_failed', 'restore_cooldown', 'restore_exhausted', 'restore_unavailable'].includes(action);
  if (restoring && episode && !episode.mailed_at && mailer && (episode.unavailable || episode.tries >= restoreMailTries
      || now - Date.parse(episode.first_seen_at) >= restoreMailMs)
      && gate.alertDue('box_interrupted', now, RESTORE_MAIL_FLOOR_SECONDS * 1000)) {
    const message = compose('box_interrupted', {
      ...facts, ...episode, box_name: box?.name ?? null, app_id: box?.app_id ?? null, app_name: box?.app_name ?? null,
      error_message: box?.error_message ?? null, status_since: box?.updated_at ?? null,
      last_checkpointed_at: box?.last_checkpointed_at ?? null, checkpoint_generation: box?.checkpoint_generation ?? null,
      cooldown_minutes: Math.round(restoreCooldown / 60000), max_tries: restoreMaxTries,
    });
    try {
      await mailer({ from: env.ALERT_FROM || FROM, to: env.ALERT_TO || TO, ...message, at: now });
      gate.recordAlert('box_interrupted', now);
      episode.mailed_at = at;
      gate.recordWatchdog({ restore: episode });
      sent.push('box_interrupted');
    } catch (error) {
      gate.recordWatchdog({ last_mail_error: error?.name || 'send_failed', last_mail_error_at: at });
    }
  }
  if (!restoring && (recoveryFailed || (stopped && !recoveredNow) || stillQuiet)) await send('box_not_running');
  if (facts.kill_switch) await send('kill_switch_engaged');
  if (gate.capsExhausted(now)) await send('caps_exhausted');
  if (new Date(now).getUTCHours() === DIGEST_UTC_HOUR) await send('daily_digest');

  return { action, at, age_seconds: age, box_status: status, balance_usd: balance, alerts: sent, ...record };
}
