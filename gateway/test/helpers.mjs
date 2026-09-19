// Test material. Every key here is generated in-process for the test that uses it: this suite
// never reads a real credential, and there is nothing key-shaped in the repository to leak.

import { createPrivateKey } from 'node:crypto';

export const TOKEN = 'gateway-token-that-is-long-enough-1234567890';

export const pem = (label, der) =>
  `-----BEGIN ${label}-----\n${Buffer.from(der).toString('base64').match(/.{1,64}/g).join('\n')}\n-----END ${label}-----\n`;

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
