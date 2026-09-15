// Kalshi request signing (https://docs.kalshi.com/getting_started/api_keys).
//
//   KALSHI-ACCESS-KEY        the key id
//   KALSHI-ACCESS-TIMESTAMP  milliseconds since the epoch, decimal
//   KALSHI-ACCESS-SIGNATURE  base64(RSA-PSS-SHA256(timestamp + METHOD + path))
//
// The signed path carries the `/trade-api/v2` prefix and excludes the query string. PSS uses a
// salt the length of the digest, which for SHA-256 is 32 bytes.

import { readPem, pkcs1ToPkcs8 } from './pem.mjs';

export const HOST = 'https://api.elections.kalshi.com';
export const PREFIX = '/trade-api/v2';
export const SALT_LENGTH = 32;

// One isolate signs many requests with one key; importing it per request is pure waste.
let cached = null;

/** Import a Kalshi RSA private key, accepting either PKCS#8 or PKCS#1 PEM. */
export async function importPrivateKey(pem) {
  const block = readPem(pem);
  if (!block) throw new Error('kalshi private key is not a PEM block');
  if (block.label === 'ENCRYPTED PRIVATE KEY') throw new Error('kalshi private key is encrypted');
  const der =
    block.label === 'RSA PRIVATE KEY' ? pkcs1ToPkcs8(block.der)
    : block.label === 'PRIVATE KEY' ? block.der
    : null;
  if (!der) throw new Error(`kalshi private key: unsupported PEM label ${block.label}`);
  return crypto.subtle.importKey(
    'pkcs8', der, { name: 'RSA-PSS', hash: 'SHA-256' }, false, ['sign'],
  );
}

async function keyFor(pem) {
  if (cached && cached.pem === pem) return cached.key;
  const key = await importPrivateKey(pem);
  cached = { pem, key };
  return key;
}

/** The exact bytes Kalshi signs: `timestamp + METHOD + path`, the path prefixed and unqueried. */
export const signingInput = (timestamp, method, path) =>
  `${timestamp}${method.toUpperCase()}${path}`;

/**
 * The three authentication headers for one request.
 * `path` is the venue path without the `/trade-api/v2` prefix and without a query string.
 */
export async function authHeaders({ keyId, privateKeyPem, method, path, now = Date.now() }) {
  const timestamp = String(Math.floor(now));
  const signed = PREFIX + '/' + String(path).replace(/^\/+/, '');
  const key = await keyFor(privateKeyPem);
  const signature = await crypto.subtle.sign(
    { name: 'RSA-PSS', saltLength: SALT_LENGTH },
    key,
    new TextEncoder().encode(signingInput(timestamp, method, signed)),
  );
  return {
    'KALSHI-ACCESS-KEY': keyId,
    'KALSHI-ACCESS-TIMESTAMP': timestamp,
    'KALSHI-ACCESS-SIGNATURE': Buffer.from(signature).toString('base64'),
  };
}

/** The upstream URL one forwarded call goes to. `search` includes its leading `?`, or is empty. */
export const target = (path, search = '') =>
  `${HOST}${PREFIX}/${String(path).replace(/^\/+/, '')}${search || ''}`;
