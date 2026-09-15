// The Sail control plane, as much of it as the gateway needs: what the org's credit balance is,
// what state the box is in, and the two calls that bring it back -- resume, then restart.
//
// The API key is a Worker secret and never leaves this module's request headers. Nothing here
// returns it, records it or puts it in an error, and every failure is reduced to a short code so
// a provider's error text cannot smuggle anything into a log or an email.

export const SAILBOX_API = 'https://sailbox-api.sailresearch.com';
export const USAGE_API = 'https://api.sailresearch.com';

/** Sailbox statuses that mean the desks are not running. `creating` is on its way up, so it is not here. */
export const STOPPED = ['paused', 'sleeping', 'terminated', 'terminating', 'failed', 'create_failed',
  'interrupted_restorable', 'interrupted_unsafe_to_retry'];
/** ...and the two that can be brought back without human hands. */
export const RESUMABLE = ['paused', 'sleeping'];

const TIMEOUT = 45000;

export async function boundedText(response, maximum = 256 * 1024) {
  const reader = response.body?.getReader();
  if (!reader) return '';
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maximum) {
      await reader.cancel();
      break;
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString('utf8');
}

const code = error =>
  (error?.name === 'TimeoutError' ? 'timeout' : error?.name === 'SyntaxError' ? 'invalid_json' : 'transport');

async function call(url, { apiKey, method = 'GET', body, idempotencyKey, fetcher, maximum }) {
  const response = await fetcher(url, {
    method,
    redirect: 'manual',
    signal: AbortSignal.timeout(TIMEOUT),
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    response.body?.cancel();
    return { error: `http_${response.status}` };
  }
  return { response, text: await boundedText(response, maximum) };
}

/**
 * The org's credit balance and spend.
 * Sail reports money as fractional US **cents**, so 3106.14 is $31.06.
 */
export async function usageSummary({ apiKey, fetcher, range = '24h' }) {
  try {
    const result = await call(`${USAGE_API}/v2/usage/summary?range=${encodeURIComponent(range)}`, { apiKey, fetcher });
    if (result.error) return result;
    const body = JSON.parse(result.text);
    if (body.balance_unavailable === true || typeof body.balance !== 'number' || !Number.isFinite(body.balance)) {
      return { error: 'balance_unavailable' };
    }
    return {
      balance_usd: body.balance / 100,
      spend_usd: Number.isFinite(body.period_spend) ? body.period_spend / 100 : null,
      range: typeof body.range === 'string' ? body.range : range,
    };
  } catch (error) {
    return { error: code(error) };
  }
}

/** The box's current status, one of the lifecycle values Sail publishes. */
export async function boxStatus({ apiKey, boxId, fetcher }) {
  try {
    const result = await call(`${SAILBOX_API}/v1/sailboxes/${encodeURIComponent(boxId)}`, { apiKey, fetcher });
    if (result.error) return result;
    const body = JSON.parse(result.text);
    return { status: String(body.status || 'unknown') };
  } catch (error) {
    return { error: code(error) };
  }
}

/**
 * Bring a paused or sleeping box back. The call answers 200 either way, so the outcome is in
 * `resume_state`: `running` and `already_running` both mean it is ready.
 */
export async function resumeBox({ apiKey, boxId, fetcher, idempotencyKey }) {
  try {
    const result = await call(`${SAILBOX_API}/v1/sailboxes/${encodeURIComponent(boxId)}/resume`, {
      apiKey, fetcher, method: 'POST', idempotencyKey,
    });
    if (result.error) return result;
    const body = JSON.parse(result.text);
    const state = String(body.resume_state || '');
    return {
      resume_state: state,
      status: String(body.status || 'unknown'),
      ready: ['running', 'already_running'].includes(state),
    };
  } catch (error) {
    return { error: code(error) };
  }
}

/**
 * Start the restart script on the box and return once the exec has a durable identity.
 * The call shape -- `POST /v1/sailboxes/<box>/exec` with an `idempotency_key` -- is the one the
 * supervisor that ran this box before used, so a retry inside a window reconnects to the same
 * exec instead of starting a second restart.
 */
export async function execRestart({ apiKey, boxId, command, idempotencyKey, fetcher }) {
  try {
    const result = await call(`${SAILBOX_API}/v1/sailboxes/${encodeURIComponent(boxId)}/exec`, {
      apiKey, fetcher, method: 'POST', maximum: 32 * 1024,
      body: { command: ['sh', '-c', command], timeout: 120, background: true, idempotency_key: idempotencyKey },
    });
    if (result.error) return { started: null, detail: result.error };
    for (const line of result.text.split('\n')) {
      if (!line.trim()) continue;
      let event;
      try {
        event = JSON.parse(line);
      } catch {
        continue;
      }
      if (event.type === 'started') return { started: String(event.exec_request_id || 'started') };
      if (event.type === 'error') return { started: null, detail: String(event.error_code || 'remote_exec_failed') };
    }
    return { started: null, detail: 'exec_unconfirmed' };
  } catch (error) {
    return { started: null, detail: code(error) };
  }
}
