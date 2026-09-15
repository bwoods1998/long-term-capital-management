// Test material. Every key here is generated in-process for the test that uses it: this suite
// never reads a real credential, and there is nothing key-shaped in the repository to leak.

import { createPrivateKey } from 'node:crypto';

export const TOKEN = 'gateway-token-that-is-long-enough-1234567890';

export const pem = (label, der) =>
  `-----BEGIN ${label}-----\n${Buffer.from(der).toString('base64').match(/.{1,64}/g).join('\n')}\n-----END ${label}-----\n`;

export const b64 = bytes => Buffer.from(bytes).toString('base64');

/** An RSA-PSS SHA-256 key pair, as PKCS#8 PEM, PKCS#1 PEM and a verifying public key. */
export async function rsaKey() {
  const pair = await crypto.subtle.generateKey(
    { name: 'RSA-PSS', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    true, ['sign', 'verify'],
  );
  const pkcs8 = pem('PRIVATE KEY', await crypto.subtle.exportKey('pkcs8', pair.privateKey));
  return {
    pkcs8,
    pkcs1: createPrivateKey(pkcs8).export({ type: 'pkcs1', format: 'pem' }),
    publicKey: pair.publicKey,
  };
}

/** An Ed25519 key: the raw 32-byte seed, the 64-byte seed||public form, and a verifying key. */
export async function ed25519Key() {
  const pair = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
  const pkcs8 = new Uint8Array(await crypto.subtle.exportKey('pkcs8', pair.privateKey));
  const seed = pkcs8.slice(-32);
  const raw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return {
    seed32: b64(seed),
    seed64: b64(Buffer.concat([seed, raw])),
    pkcs8Pem: pem('PRIVATE KEY', pkcs8),
    publicKey: pair.publicKey,
  };
}

/** A P-256 key as PKCS#8 PEM, SEC1 PEM, base64 DER and a verifying key. */
export async function ecKey() {
  const pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
  const der = new Uint8Array(await crypto.subtle.exportKey('pkcs8', pair.privateKey));
  const pkcs8 = pem('PRIVATE KEY', der);
  return {
    pkcs8,
    sec1: createPrivateKey(pkcs8).export({ type: 'sec1', format: 'pem' }),
    der: b64(der),
    publicKey: pair.publicKey,
  };
}

export const decodeSegment = segment =>
  JSON.parse(Buffer.from(segment.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8'));

/** A `fetch` stand-in that records every call and replays one scripted reply. */
export function recorder(reply = { status: 200, body: '{"ok":true}' }) {
  const calls = [];
  const fetcher = async (url, options = {}) => {
    calls.push({ url: String(url), ...options });
    if (typeof reply === 'function') return reply(String(url), options);
    if (reply instanceof Error) throw reply;
    return new Response(reply.body ?? null, {
      status: reply.status ?? 200,
      headers: reply.headers ?? { 'Content-Type': 'application/json' },
    });
  };
  return { fetcher, calls };
}

/** A synchronous key/value store standing in for the Durable Object's SQLite table. */
export function memoryStore(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { get: key => map.get(key), set: (key, value) => map.set(key, value), map };
}

export const bearer = (extra = {}) => ({ Authorization: `Bearer ${TOKEN}`, ...extra });
