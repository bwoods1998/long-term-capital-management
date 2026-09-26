// The venue credentials, checked the only way that means anything: sign with the gateway's own
// code, then verify with the public half of the key it signed under.

import assert from 'node:assert/strict';
import test from 'node:test';

import * as alpaca from '../lib/alpaca.mjs';

const NOW = 1789480800000; // 2026-09-15T14:00:00Z
const encode = text => new TextEncoder().encode(text);





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
