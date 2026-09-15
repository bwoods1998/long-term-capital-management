// Replies and bearer authentication. Nothing here ever puts a credential in a body or a header
// it returns: an unauthenticated caller learns only that it was unauthenticated.

import { timingSafeEqual } from 'node:crypto';

export const HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'X-Content-Type-Options': 'nosniff',
  'Cache-Control': 'no-store',
  'Referrer-Policy': 'no-referrer',
};

export const json = (value, status = 200, extra = {}) =>
  new Response(JSON.stringify(value), { status, headers: { ...HEADERS, ...extra } });

export const fail = (message, status, extra = {}) => json({ error: message }, status, extra);

/**
 * Constant-time bearer check. A token shorter than 32 characters is treated as no token at all,
 * so a half-configured deployment refuses every request instead of accepting a guessable one.
 */
export function authorized(request, secret) {
  if (typeof secret !== 'string' || secret.length < 32) return false;
  const actual = Buffer.from(request.headers.get('Authorization') || '');
  const expected = Buffer.from(`Bearer ${secret}`);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

/** Read a request body as text, refusing anything larger than `limit` bytes. */
export async function readBody(request, limit = 256 * 1024) {
  if (!request.body) return { text: null };
  const declared = Number(request.headers.get('Content-Length') || 0);
  if (Number.isFinite(declared) && declared > limit) return { error: 'Payload too large.' };
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel();
      return { error: 'Payload too large.' };
    }
    chunks.push(value);
  }
  if (!size) return { text: null };
  return { text: Buffer.concat(chunks).toString('utf8') };
}

export const b64url = bytes =>
  Buffer.from(bytes).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

export const iso = ms => new Date(ms).toISOString();
