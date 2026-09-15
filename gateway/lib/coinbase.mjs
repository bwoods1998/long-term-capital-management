// Coinbase CDP JWT minting (https://docs.cdp.coinbase.com/api-reference/v2/authentication).
//
//   header  { alg: "EdDSA" | "ES256", kid: <key id>, nonce: <random hex>, typ: "JWT" }
//   payload { sub: <key id>, iss: "cdp", nbf: now, exp: now + 120,
//             uri: "METHOD api.coinbase.com/<path>" }
//
// The `uri` claim binds a token to one method and one path, so a token is minted per request and
// never reused. A CDP secret arrives as an Ed25519 secret in base64 -- 64 bytes of 32-byte seed
// followed by the public key, or the bare 32-byte seed -- as DER, or as a PEM.

import { readPem, sec1ToPkcs8, ed25519SeedToPkcs8, fromBase64 } from './pem.mjs';
import { b64url } from './http.mjs';

export const HOST = 'https://api.coinbase.com';
export const API_HOST = 'api.coinbase.com';
export const LIFETIME_SECONDS = 120;

let cached = null;

/** `{ key, algorithm }` for a CDP secret in any of the forms the portal hands out. */
export async function importSecret(secret) {
  const text = String(secret || '').trim();
  if (!text) throw new Error('coinbase secret is empty');
  if (text.includes('PRIVATE KEY')) {
    const block = readPem(text);
    if (!block) throw new Error('coinbase secret is not a PEM block');
    if (block.label === 'ENCRYPTED PRIVATE KEY') throw new Error('coinbase secret is encrypted');
    if (block.label === 'EC PRIVATE KEY') return importEc(sec1ToPkcs8(block.der));
    if (block.label !== 'PRIVATE KEY') throw new Error(`coinbase secret: unsupported PEM label ${block.label}`);
    return importPkcs8(block.der);
  }
  const bytes = fromBase64(text);
  if (!bytes) throw new Error('coinbase secret is neither PEM nor base64');
  if (bytes.length === 32 || bytes.length === 64) return importEd25519(ed25519SeedToPkcs8(bytes.slice(0, 32)));
  return importPkcs8(bytes);
}

// A bare PKCS#8 blob does not say which curve it holds until it is parsed, so the two algorithms
// this venue issues are simply tried in turn; WebCrypto rejects the wrong one.
async function importPkcs8(der) {
  try {
    return await importEd25519(der);
  } catch {
    return importEc(der);
  }
}

const importEd25519 = async der => ({
  key: await crypto.subtle.importKey('pkcs8', der, { name: 'Ed25519' }, false, ['sign']),
  algorithm: 'EdDSA',
});

const importEc = async der => ({
  key: await crypto.subtle.importKey('pkcs8', der, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']),
  algorithm: 'ES256',
});

async function keyFor(secret) {
  if (cached && cached.secret === secret) return cached.imported;
  const imported = await importSecret(secret);
  cached = { secret, imported };
  return imported;
}

export const randomNonce = () =>
  [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');

/**
 * One CDP JWT for the Advanced Trade WebSocket user channel. Same key, same header, but the
 * claim set carries no `uri` (and no `aud`): the socket is not one method and one path
 * (https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-overview).
 * The docs' Python sample says `iss: "coinbase-cloud"`; their JavaScript sample and every REST
 * sample say `"cdp"`, which is what the REST path already uses successfully, so `"cdp"` it is.
 * Two minutes long; the VM mints one per subscribe message and never holds the key.
 */
export async function mintWsJwt({ keyName, secret, now = Date.now(), nonce = randomNonce() }) {
  const { key, algorithm } = await keyFor(secret);
  const seconds = Math.floor(now / 1000);
  const header = { alg: algorithm, kid: keyName, nonce, typ: 'JWT' };
  const payload = { sub: keyName, iss: 'cdp', nbf: seconds, exp: seconds + LIFETIME_SECONDS };
  const signingInput =
    b64url(Buffer.from(JSON.stringify(header))) + '.' + b64url(Buffer.from(JSON.stringify(payload)));
  const parameters = algorithm === 'EdDSA' ? { name: 'Ed25519' } : { name: 'ECDSA', hash: 'SHA-256' };
  const signature = await crypto.subtle.sign(parameters, key, new TextEncoder().encode(signingInput));
  return signingInput + '.' + b64url(new Uint8Array(signature));
}

/**
 * One CDP JWT for `METHOD api.coinbase.com/<path>`.
 * `path` is the venue path without a leading slash and without a query string.
 */
export async function mintJwt({ keyName, secret, method, path, now = Date.now(), nonce = randomNonce() }) {
  const { key, algorithm } = await keyFor(secret);
  const seconds = Math.floor(now / 1000);
  const header = { alg: algorithm, kid: keyName, nonce, typ: 'JWT' };
  const payload = {
    sub: keyName,
    iss: 'cdp',
    nbf: seconds,
    exp: seconds + LIFETIME_SECONDS,
    uri: `${method.toUpperCase()} ${API_HOST}/${String(path).replace(/^\/+/, '')}`,
  };
  const signingInput =
    b64url(Buffer.from(JSON.stringify(header))) + '.' + b64url(Buffer.from(JSON.stringify(payload)));
  // WebCrypto already returns ECDSA signatures as the raw `r || s` a JWS wants, not a DER sequence.
  const parameters = algorithm === 'EdDSA' ? { name: 'Ed25519' } : { name: 'ECDSA', hash: 'SHA-256' };
  const signature = await crypto.subtle.sign(parameters, key, new TextEncoder().encode(signingInput));
  return signingInput + '.' + b64url(new Uint8Array(signature));
}

export const target = (path, search = '') =>
  `${HOST}/${String(path).replace(/^\/+/, '')}${search || ''}`;
