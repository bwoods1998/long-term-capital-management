// The two signing recipes, checked the only way that means anything: sign with the gateway's own
// code, then verify with the public half of the key it signed under.

import assert from 'node:assert/strict';
import test from 'node:test';

import * as kalshi from '../lib/kalshi.mjs';
import * as coinbase from '../lib/coinbase.mjs';
import { rsaKey, ed25519Key, ecKey, decodeSegment, pem } from './helpers.mjs';

const NOW = 1789480800000; // 2026-09-15T14:00:00Z
const encode = text => new TextEncoder().encode(text);

test('kalshi signs timestamp + METHOD + prefixed path with RSA-PSS, salt 32', async () => {
  const key = await rsaKey();
  const headers = await kalshi.authHeaders({
    keyId: 'a1b2', privateKeyPem: key.pkcs8, method: 'get', path: 'portfolio/balance', now: NOW,
  });
  assert.equal(headers['KALSHI-ACCESS-KEY'], 'a1b2');
  assert.equal(headers['KALSHI-ACCESS-TIMESTAMP'], String(NOW));
  const verified = await crypto.subtle.verify(
    { name: 'RSA-PSS', saltLength: 32 },
    key.publicKey,
    Buffer.from(headers['KALSHI-ACCESS-SIGNATURE'], 'base64'),
    encode(`${NOW}GET/trade-api/v2/portfolio/balance`),
  );
  assert.equal(verified, true);
});

test('kalshi accepts a PKCS#1 private key as well as PKCS#8', async () => {
  const key = await rsaKey();
  const headers = await kalshi.authHeaders({
    keyId: 'k', privateKeyPem: key.pkcs1, method: 'POST', path: '/portfolio/events/orders', now: NOW,
  });
  const verified = await crypto.subtle.verify(
    { name: 'RSA-PSS', saltLength: 32 },
    key.publicKey,
    Buffer.from(headers['KALSHI-ACCESS-SIGNATURE'], 'base64'),
    encode(`${NOW}POST/trade-api/v2/portfolio/events/orders`),
  );
  assert.equal(verified, true);
});

test('kalshi refuses a key it cannot use, and never signs with the wrong message', async () => {
  await assert.rejects(() => kalshi.importPrivateKey('not a pem'), /not a PEM/);
  await assert.rejects(() => kalshi.importPrivateKey(pem('ENCRYPTED PRIVATE KEY', new Uint8Array([1]))), /encrypted/);
  assert.equal(kalshi.signingInput('17', 'delete', '/trade-api/v2/x'), '17DELETE/trade-api/v2/x');
});

test('kalshi forwards to the elections host under the v2 prefix, query intact', () => {
  assert.equal(
    kalshi.target('portfolio/orders', '?status=resting&limit=200'),
    'https://api.elections.kalshi.com/trade-api/v2/portfolio/orders?status=resting&limit=200',
  );
});

test('coinbase mints an EdDSA JWT from a 32-byte Ed25519 seed', async () => {
  const key = await ed25519Key();
  const token = await coinbase.mintJwt({
    keyName: 'organizations/o/apiKeys/k', secret: key.seed32,
    method: 'get', path: 'api/v3/brokerage/accounts', now: NOW, nonce: 'ab'.repeat(16),
  });
  const [head, claims, signature] = token.split('.');
  assert.deepEqual(decodeSegment(head), {
    alg: 'EdDSA', kid: 'organizations/o/apiKeys/k', nonce: 'ab'.repeat(16), typ: 'JWT',
  });
  assert.deepEqual(decodeSegment(claims), {
    sub: 'organizations/o/apiKeys/k', iss: 'cdp', nbf: NOW / 1000, exp: NOW / 1000 + 120,
    uri: 'GET api.coinbase.com/api/v3/brokerage/accounts',
  });
  const verified = await crypto.subtle.verify(
    { name: 'Ed25519' }, key.publicKey,
    Buffer.from(signature.replace(/-/g, '+').replace(/_/g, '/'), 'base64'),
    encode(`${head}.${claims}`),
  );
  assert.equal(verified, true);
});

test('coinbase accepts the 64-byte seed||public form and an Ed25519 PEM', async () => {
  for (const key of [await ed25519Key(), await ed25519Key()]) {
    for (const secret of [key.seed64, key.pkcs8Pem]) {
      const token = await coinbase.mintJwt({
        keyName: 'k', secret, method: 'POST', path: '/api/v3/brokerage/orders', now: NOW,
      });
      const [head, claims, signature] = token.split('.');
      assert.equal(decodeSegment(head).alg, 'EdDSA');
      assert.equal(decodeSegment(claims).uri, 'POST api.coinbase.com/api/v3/brokerage/orders');
      assert.equal(
        await crypto.subtle.verify(
          { name: 'Ed25519' }, key.publicKey,
          Buffer.from(signature.replace(/-/g, '+').replace(/_/g, '/'), 'base64'),
          encode(`${head}.${claims}`),
        ),
        true,
      );
    }
  }
});

test('coinbase signs ES256 as raw r||s for a PKCS#8, SEC1 or DER key', async () => {
  const key = await ecKey();
  for (const secret of [key.pkcs8, key.sec1, key.der]) {
    const token = await coinbase.mintJwt({ keyName: 'k', secret, method: 'GET', path: 'api/v3/brokerage/accounts', now: NOW });
    const [head, claims, signature] = token.split('.');
    assert.equal(decodeSegment(head).alg, 'ES256');
    const raw = Buffer.from(signature.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
    assert.equal(raw.length, 64, 'a JWS signature is r||s, never a DER sequence');
    assert.equal(
      await crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, key.publicKey, raw, encode(`${head}.${claims}`)),
      true,
    );
  }
});

test('coinbase gives every request a fresh nonce and refuses an unusable secret', async () => {
  assert.notEqual(coinbase.randomNonce(), coinbase.randomNonce());
  assert.match(coinbase.randomNonce(), /^[0-9a-f]{32}$/);
  await assert.rejects(() => coinbase.importSecret(''), /empty/);
  await assert.rejects(() => coinbase.importSecret('!!!not base64!!!'), /neither PEM nor base64/);
  assert.equal(coinbase.target('api/v3/brokerage/accounts', '?limit=250'),
    'https://api.coinbase.com/api/v3/brokerage/accounts?limit=250');
});
