// The venue credentials, checked the only way that means anything: sign with the gateway's own
// code, then verify with the public half of the key it signed under.

import assert from 'node:assert/strict';
import test from 'node:test';

import * as kalshi from '../lib/kalshi.mjs';
import * as alpaca from '../lib/alpaca.mjs';
import { rsaKey, pem } from './helpers.mjs';

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

test('alpaca is two headers, and the path chooses the trading or the data host', () => {
  assert.deepEqual(alpaca.authHeaders({ keyId: ' AK1 ', secretKey: 's3cret\n' }),
    { 'APCA-API-KEY-ID': 'AK1', 'APCA-API-SECRET-KEY': 's3cret' });
  assert.throws(() => alpaca.authHeaders({ keyId: '', secretKey: 's' }), /key id/);
  assert.throws(() => alpaca.authHeaders({ keyId: 'k', secretKey: ' ' }), /secret key/);
  assert.equal(alpaca.target('v2/orders', '?status=open'), 'https://api.alpaca.markets/v2/orders?status=open');
  assert.equal(alpaca.target('/v2/stocks/AAPL/quotes/latest'), 'https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest');
  assert.equal(alpaca.target('v1beta3/crypto/us/latest/quotes', '?symbols=BTC%2FUSD'),
    'https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD');
});
