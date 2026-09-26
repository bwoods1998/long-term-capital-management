// Long-Term Capital Management order gateway.
//
// The desks run in a cloud VM. The venue private keys do not: they are Worker secrets here, and
// the VM holds nothing but a bearer token. So the worst a compromised VM can do is ask this
// Worker for an order, and this Worker will only sign one that is inside the caps below and only
// while the kill switch -- which also lives here, not in the VM -- is open.
//
// Everything decided here is decided in one Durable Object, so two desks submitting at the same
// instant cannot both spend the last of the day's budget.

import { DurableObject } from 'cloudflare:workers';
import { EmailMessage } from 'cloudflare:email';
import { createGate, GATE_OBJECT } from './lib/gate.mjs';
import { runWatchdog } from './lib/watchdog.mjs';
import { route } from './lib/router.mjs';
import { mime } from './lib/email.mjs';
import { json } from './lib/http.mjs';

// Mail is the only way this system asks for a human. Without the binding it simply does not ask,
// and the watchdog keeps working: the alert is recorded as unsent rather than lost.
const mailerFor = env =>
  (env.EMAIL
    ? async ({ from, to, subject, text, at }) =>
        env.EMAIL.send(new EmailMessage(from, to, mime({ from, to, subject, text, at })))
    : null);

const SCHEMA = 'CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)';
const UPSERT =
  'INSERT INTO state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value';

export class Gate extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    const sql = ctx.storage.sql;
    sql.exec(SCHEMA);
    this.gate = createGate({
      env,
      store: {
        get: key => sql.exec('SELECT value FROM state WHERE key = ?', key).toArray()[0]?.value,
        set: (key, value) => sql.exec(UPSERT, key, value),
      },
    });
  }

  status() { return this.gate.status(); }
  // The real Alpaca account's equity for the caps by maximum loss (Sept 26, 2026 (the options-swarm run, Wave 5)).
  accountEquity() { return this.gate.accountEquity(); }
  recordAccountEquity(reading) { return this.ctx.storage.transactionSync(() => this.gate.recordAccountEquity(reading)); }
  setKill(on) { return this.gate.setKill(on === true); }
  noticesToday(at) { return this.gate.noticesToday(at); }
  noticeDelivered(id, at) { return this.gate.noticeDelivered(id, at); }
  recordNotice(at, id) { return this.gate.recordNotice(at, id); }

  // One transaction, no await inside it: the check and the spend are the same step.
  reserve(request) { return this.ctx.storage.transactionSync(() => this.gate.reserve(request)); }
  refund(request) { return this.ctx.storage.transactionSync(() => this.gate.refund(request)); }
  frontierReserve(request) { return this.ctx.storage.transactionSync(() => this.gate.frontierReserve(request)); }
  frontierSettle(request) { return this.ctx.storage.transactionSync(() => this.gate.frontierSettle(request)); }
  pullReserve(request) { return this.ctx.storage.transactionSync(() => this.gate.pullReserve(request)); }
  pullRefund(request) { return this.ctx.storage.transactionSync(() => this.gate.pullRefund(request)); }

  watchdog() { return runWatchdog({ gate: this.gate, env: this.env, mailer: mailerFor(this.env) }); }
}

const gateOf = env => env.GATE.get(env.GATE.idFromName(GATE_OBJECT));

export default {
  async scheduled(controller, env) {
    await gateOf(env).watchdog();
  },

  async fetch(request, env) {
    // A refusal before any route names its cap, so the House never reads it as a lost order (Sept 26, 2026, Wave 5).
    if (!env.GATE) return json({ error: 'Gateway setup is incomplete.', cap: 'setup' }, 503);
    return route(request, env, { gate: gateOf(env), mailer: mailerFor(env) });
  },
};
