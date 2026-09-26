import assert from 'node:assert/strict';
import test from 'node:test';
import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

test('retired venue, semantic and fetch routes cannot read credentials or call upstream', async () => {
  const gate = createGate({ store: memoryStore() });
  let calls = 0;
  const env = { GATEWAY_TOKEN: TOKEN };
  for (const path of ['/v1/kalshi/portfolio/orders','/v1/kalshi/ws-auth','/v1/typesafe/systemone','/v1/web/fetch']) {
    const response = await route(new Request('https://gw.test'+path,{method:'POST',headers:{Authorization:'Bearer '+TOKEN},body:'{}'}),
      env,{gate,fetcher:()=>{calls++;throw new Error('upstream forbidden');}});
    assert.equal(response.status,404,path);
  }
  assert.equal(calls,0);
  assert.equal(gate.reserve({venue:'kalshi',micro:'1'}).cap,'venue');
  const health = gate.status();
  for (const old of ['typesafe','web_fetch']) assert.equal(health[old],undefined);
  assert.equal(health.frontier.profit_index,undefined);
});
