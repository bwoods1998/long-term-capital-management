// Multi-leg structures (Sept 25, 2026, the options-desk run): what the gateway reads a multi-leg
// order as, which structures it admits, and what one is worth. The rules are the structure spec's
// (`league/structures.py`), read here from the venue's own order body without being told the type.

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  notional, structureOrder, structureNotional, classifyStructure, practiceOrderError, admittedStructures,
  isMultiLegOrder, STRUCTURE_TYPES, NAKED_SHORT, UNCOVERED_RATIO,
} from '../lib/caps.mjs';
import { formatUsd } from '../lib/money.mjs';
import { occ, leg, mleg, closing, OPENS, BTO, STO, STC, BTC } from './structures-fixtures.mjs';

const usd = micro => formatUsd(micro);

test('every defined-risk type of the spec is read from its legs, opened and closed', () => {
  const seen = new Set();
  for (const [type, legs, limit, maxLoss] of OPENS) {
    const opened = structureOrder(mleg(legs, limit));
    assert.equal(opened.error, undefined, `${type} ${limit}: ${opened.error}`);
    assert.equal(opened.type, type);
    assert.equal(opened.opening, true);
    assert.equal(usd(opened.maxLossMicro), maxLoss, `${type}: its maximum loss`);
    // The legs in any order are the same structure.
    assert.equal(structureOrder(mleg([...legs].reverse(), limit)).type, type);
    // Closed whole: a debit structure is sold for a credit (negative), a credit one bought back for a debit (positive).
    const credit = type.startsWith('credit') || type.startsWith('iron');
    const closed = structureOrder(mleg(closing(legs), credit ? '0.10' : '-0.05'));
    assert.equal(closed.error, undefined, `${type} close: ${closed.error}`);
    assert.equal(closed.type, type);
    assert.equal(closed.opening, false);
    assert.equal(closed.maxLossMicro, 0n, 'a close takes risk off');
    seen.add(type);
  }
  assert.deepEqual([...seen].sort(), [...STRUCTURE_TYPES].sort(), 'the fixtures cover every type');
});

test('classifyStructure reads the legs alone: collateral and maximum value in picodollars a share', () => {
  const at = (strike, right, sign, ratio = 1, expiry = '260928') => ({ expiry, right, strike: BigInt(strike * 1000), sign, ratio });
  const PICO = 10n ** 12n;
  assert.deepEqual(classifyStructure([at(581, 'C', -1), at(580, 'C', 1)]), { type: 'debit_vertical', collateral: 0n, maxValue: PICO });
  assert.deepEqual(classifyStructure([at(580, 'P', -1), at(582, 'P', 1)]), { type: 'debit_vertical', collateral: 0n, maxValue: 2n * PICO });
  assert.deepEqual(classifyStructure([at(582, 'P', -1), at(580, 'P', 1)]), { type: 'credit_vertical', collateral: 2n * PICO, maxValue: 2n * PICO });
  assert.equal(classifyStructure([at(585, 'C', 1, 1, '261002'), at(585, 'C', -1)]).type, 'calendar');
  assert.equal(classifyStructure([at(580, 'C', -1), at(581, 'C', -1)]).error, NAKED_SHORT);
  for (const legs of [[], [at(580, 'C', 1)], [1, 2, 3, 4, 5].map(n => at(580 + n, 'C', 1)), null]) {
    assert.match(classifyStructure(legs).error, /two to four legs/);
  }
});

test('the maximum loss is the debit, or the collateral less the credit, x 100 x qty', () => {
  // The spec's example: a $1-wide SPY iron condor for a $0.38 credit is held at 0.62, $62 at risk.
  const [, condor] = OPENS.find(([type]) => type === 'iron_condor');
  assert.equal(usd(structureOrder(mleg(condor, '-0.38')).maxLossMicro), '62.00');
  assert.equal(usd(structureOrder(mleg(condor, '-0.38', { qty: '3' })).maxLossMicro), '186.00');
  // The collateral is the WIDER wing: a $1 put wing and a $2 call wing hold $2 a share.
  const wide = [leg(occ(579, 'P'), BTO), leg(occ(580, 'P'), STO), leg(occ(590), STO), leg(occ(592), BTO)];
  const read = structureOrder(mleg(wide, '-0.50'));
  assert.equal(read.type, 'iron_condor');
  assert.equal(usd(read.maxLossMicro), '150.00');
  // A debit vertical is its debit, a fraction of a cent rounds against the order.
  assert.equal(usd(structureOrder(mleg(OPENS[0][1], '0.705')).maxLossMicro), '70.50');
  assert.equal(usd(structureOrder(mleg(OPENS[0][1], 0.7, { qty: 2 })).maxLossMicro), '140.00', 'JSON numbers read like strings');
});

test('a naked short is refused, alone or inside a multi-leg order', () => {
  // Inside a multi-leg order: a short leg whose right has no long leg.
  for (const legs of [
    [leg(occ(580, 'P'), STO), leg(occ(590), BTO)],                       // a risk reversal: the put is naked
    [leg(occ(590), STO), leg(occ(591), STO)],                             // two short calls
    [leg(occ(579, 'P'), BTO), leg(occ(580, 'P'), STO), leg(occ(590), STO)], // a condor missing its long call
    [leg(occ(580, 'P'), STO), leg(occ(585, 'P'), STO), leg(occ(590), BTO), leg(occ(595), BTO)],
  ]) {
    assert.equal(structureOrder(mleg(legs, '-0.40')).error, NAKED_SHORT, JSON.stringify(legs.map(row => row.symbol)));
    assert.equal(practiceOrderError(mleg(legs, '-0.40')), NAKED_SHORT);
  }
  // A single option sold to open, on the practice account.
  const single = { symbol: occ(580, 'P'), qty: '1', side: 'sell', type: 'limit', limit_price: '0.25', time_in_force: 'day', position_intent: STO };
  assert.equal(practiceOrderError(single),
    'A single option sold to open is a naked short (a short leg with no long leg covering it): refused. A short leg is sold only inside a multi-leg order whose long legs cover it.');
  // Nor may the venue be left to infer one: a sell with no intent, or with an intent its side contradicts.
  const { position_intent: _, ...bare } = single;
  assert.match(practiceOrderError(bare), /names its position_intent/);
  assert.match(practiceOrderError({ ...single, position_intent: 'SELL_TO_OPEN' }), /names its position_intent/);
  assert.match(practiceOrderError({ ...single, position_intent: BTO }), /buy_to_open order is a buy: its side says otherwise/);
  // A multi-leg order of one leg is no structure.
  assert.match(structureOrder(mleg([leg(occ(580, 'P'), STO)], '-0.25')).error, /two to four legs/);
});

test('a ratio other than a long butterfly\'s body, and a broken wing, are refused', () => {
  // A 1x2 call ratio spread: one short call is covered, the other is not.
  assert.equal(structureOrder(mleg([leg(occ(580), BTO), leg(occ(581), STO, '2')], '0.10')).error, UNCOVERED_RATIO);
  assert.equal(structureOrder(mleg([leg(occ(580), BTO, '2'), leg(occ(581), STO)], '0.10')).error, UNCOVERED_RATIO);
  assert.equal(structureOrder(mleg([leg(occ(579, 'P'), BTO), leg(occ(580, 'P'), STO, '2'), leg(occ(590), STO), leg(occ(591), BTO)], '-0.40')).error, UNCOVERED_RATIO);
  // A butterfly's body of two covered by only one long call, the other long being a put.
  assert.equal(structureOrder(mleg([leg(occ(580), BTO), leg(occ(581), STO, '2'), leg(occ(582, 'P'), BTO)], '0.10')).error, UNCOVERED_RATIO);
  // A ratio of three is never a leg's.
  assert.match(structureOrder(mleg([leg(occ(580), BTO), leg(occ(581), STO, '3'), leg(occ(582), BTO)], '0.10')).error, /ratio_qty is 1, or 2/);
  // A broken wing: $1 below the body and $2 above it.
  assert.equal(structureOrder(mleg([leg(occ(580), BTO), leg(occ(581), STO, '2'), leg(occ(583), BTO)], '0.10')).error,
    'A broken-wing butterfly (unequal wings) can lose more than its debit: refused.');
  // A 1:1:1 "butterfly" is not one.
  assert.match(structureOrder(mleg([leg(occ(580), BTO), leg(occ(581), STO), leg(occ(582), BTO)], '0.10')).error, /only as a long butterfly/);
});

test('a reversed vertical sent as a debit is refused: its legs make it a credit vertical, and a debit on one pays to sell it', () => {
  // The strategy meant a debit call vertical (long 580, short 581) and sent the legs reversed.
  const reversed = [leg(occ(581), BTO), leg(occ(580), STO)];
  assert.equal(structureOrder(mleg(reversed, '-0.40')).type, 'credit_vertical');
  assert.equal(structureOrder(mleg(reversed, '0.40')).error,
    'Opening a credit_vertical takes in a credit, which Alpaca\'s multi-leg limit_price writes as a negative number (a debit positive, a credit negative): a positive limit_price on it is the wrong sign, refused.');
  // And the other way: a debit structure opened at a credit, closes at the wrong sign.
  assert.match(structureOrder(mleg(OPENS[0][1], '-0.55')).error, /Opening a debit_vertical pays a debit.*a negative limit_price on it is the wrong sign/);
  assert.match(structureOrder(mleg(closing(OPENS[0][1]), '0.55')).error, /Closing a debit_vertical sells it for a credit.*a positive limit_price/);
  assert.match(structureOrder(mleg(closing(OPENS[2][1]), '-0.10')).error, /Closing a credit_vertical buys it back for a debit.*a negative limit_price/);
  // Zero says neither debit nor credit.
  for (const limit of ['0', '0.00', '-0', 0, undefined, 'x', '']) {
    assert.match(structureOrder(mleg(OPENS[0][1], limit)).error, /needs a limit_price/, JSON.stringify(limit));
  }
});

test('a limit that could never pay, or a credit at or over its collateral, is refused as the spec refuses it', () => {
  assert.equal(structureOrder(mleg(OPENS[0][1], '1.00')).error, 'A debit of 1.00 on a debit_vertical worth at most 1.00 can never pay: refused.');
  assert.match(structureOrder(mleg(OPENS[6][1], '1.20')).error, /long_butterfly worth at most 1\.00 can never pay/);
  assert.equal(structureOrder(mleg(OPENS[2][1], '-1.00')).error, 'A credit of 1.00 on a credit_vertical with 1.00 of collateral is not a defined-risk order: refused.');
  assert.match(structureOrder(mleg(closing(OPENS[4][1]), '1.05')).error, /A buy-back of 1\.05 on an iron_condor with 1\.00 of collateral/);
  // Unbounded types have no ceiling on their debit.
  assert.equal(structureOrder(mleg(OPENS[11][1], '9.00')).type, 'long_straddle');
});

test('a contract twice, mixed underlyings, and a mix of opening and closing legs are refused', () => {
  assert.equal(structureOrder(mleg([leg(occ(580), BTO), leg(occ(580), STO)], '0.10')).error, 'A contract appears twice in one order.');
  assert.equal(structureOrder(mleg([leg(occ(580), BTO), leg(occ(581, 'C', '260928', 'QQQ'), STO)], '0.10')).error,
    'Every leg of a structure is on one underlying (one OCC root).');
  const legging = 'An order that opens some legs and closes others is legging in or out, or a roll: refused. A structure opens whole (every leg *_to_open) and closes whole (every leg *_to_close).';
  // Legging out of a vertical's long leg while opening a new short, and the documented roll.
  assert.equal(structureOrder(mleg([leg(occ(580), STC), leg(occ(581), STO)], '-0.10')).error, legging);
  assert.equal(structureOrder(mleg([leg(occ(580), BTC), leg(occ(585), STC), leg(occ(590), STO), leg(occ(595), BTO)], '2.05')).error, legging);
});

test('calendars and diagonals: the short leg expires first, and a diagonal\'s long strike is at least as good', () => {
  assert.equal(structureOrder(mleg([leg(occ(585, 'C', '261002'), STO), leg(occ(585, 'C', '260928'), BTO)], '0.40')).error,
    'A short leg that expires after the long leg covering it is naked once the long leg expires: refused.');
  const call = structureOrder(mleg([leg(occ(585, 'C', '260928'), STO), leg(occ(586, 'C', '261002'), BTO)], '0.40'));
  assert.equal(call.error, 'A diagonal whose long leg\'s strike is less favourable than its short leg\'s (a higher call, a lower put) can lose more than its debit: refused.');
  assert.equal(structureOrder(mleg([leg(occ(585, 'P', '260928'), STO), leg(occ(584, 'P', '261002'), BTO)], '0.40')).error, call.error);
  // Two long legs are a structure only as a straddle or strangle.
  assert.match(structureOrder(mleg([leg(occ(580), BTO), leg(occ(581), BTO)], '1.00')).error, /long straddle or strangle/);
  assert.match(structureOrder(mleg([leg(occ(585, 'C', '260928'), BTO), leg(occ(585, 'P', '261002'), BTO)], '1.00')).error, /long straddle or strangle/);
});

test('an iron condor whose wings are inside out, or of two expiries, is refused', () => {
  const four = /only as an iron condor or iron butterfly/;
  // Short put above the short call.
  assert.match(structureOrder(mleg([leg(occ(579, 'P'), BTO), leg(occ(592, 'P'), STO), leg(occ(590), STO), leg(occ(595), BTO)], '-0.40')).error, four);
  // A long "condor" (buy the inner strikes, sell the outer ones) is not a spec type.
  assert.match(structureOrder(mleg([leg(occ(579, 'P'), STO), leg(occ(580, 'P'), BTO), leg(occ(590), BTO), leg(occ(591), STO)], '0.40')).error, four);
  // Two expiries.
  assert.match(structureOrder(mleg([leg(occ(579, 'P'), BTO), leg(occ(580, 'P'), STO), leg(occ(590, 'C', '261002'), STO), leg(occ(591, 'C', '261002'), BTO)], '-0.40')).error, four);
  // An all-call condor.
  assert.match(structureOrder(mleg([leg(occ(579), BTO), leg(occ(580), STO), leg(occ(590), STO), leg(occ(591), BTO)], '-0.40')).error, four);
});

test('the order around the legs: limit, day, whole structures, no top-level symbol or side, only the documented fields', () => {
  const legs = OPENS[0][1];
  const cases = [
    [mleg(legs, '0.55', { type: 'market' }), /limit order/],
    [mleg(legs, '0.55', { time_in_force: 'gtc' }), /day order/],
    [mleg(legs, '0.55', { qty: '0.5' }), /whole number of structures/],
    [mleg(legs, '0.55', { qty: '0' }), /whole number of structures/],
    [mleg(legs, '0.55', { symbol: 'SPY' }), /no top-level symbol/],
    [mleg(legs, '0.55', { side: 'buy' }), /field "side" is not one this gateway reads/],
    [mleg(legs, '0.55', { position_intent: BTO }), /field "position_intent"/],
    [mleg(legs, '0.55', { extended_hours: true }), /field "extended_hours"/],
    [mleg(legs, '0.55', { Legs: [] }), /field "Legs"/],
    [mleg(legs, '0.55', { order_class: 'MLEG' }), /order_class "mleg"/],
    [mleg([...legs, leg(occ(582), BTO), leg(occ(583), BTO), leg(occ(584), BTO)], '0.55'), /two to four legs/],
    [mleg('x', '0.55'), /two to four legs/],
    [mleg([{ ...legs[0], Side: 'sell' }, legs[1]], '0.55'), /Leg field "Side"/],
    [mleg([{ ...legs[0], side: 'sell' }, legs[1]], '0.55'), /buy_to_open leg is a buy: its side says otherwise/],
    [mleg([{ ...legs[0], position_intent: 'open' }, legs[1]], '0.55'), /names its position_intent/],
    [mleg([leg('SPY1260928C00580000', BTO), legs[1]], '0.55'), /standard OCC option symbol/],
    [mleg([leg(occ(580).toLowerCase(), BTO), legs[1]], '0.55'), /standard OCC option symbol/],
    [mleg([leg('SPY', BTO), legs[1]], '0.55'), /standard OCC option symbol/],
    [mleg([null, legs[1]], '0.55'), /A leg is an object/],
  ];
  for (const [body, pattern] of cases) assert.match(structureOrder(body).error ?? '', pattern, JSON.stringify(body));
  // A body with legs but no mleg class is still read as a multi-leg order, and refused.
  const { order_class: _, ...classless } = mleg(legs, '0.55');
  assert.ok(isMultiLegOrder(classless));
  assert.match(practiceOrderError(classless), /order_class "mleg"/);
  assert.match(practiceOrderError({ ...classless, order_class: 'simple', symbol: 'SPY', side: 'buy' }), /order_class "mleg"/);
});

test('OPTION_STRUCTURES_REAL admits the types it names, and a typo admits none', () => {
  assert.deepEqual(admittedStructures({}), []);
  assert.deepEqual(admittedStructures({ OPTION_STRUCTURES_REAL: 'off' }), []);
  assert.deepEqual(admittedStructures({ OPTION_STRUCTURES_REAL: 'OFF' }), []);
  assert.deepEqual(admittedStructures({ OPTION_STRUCTURES_REAL: '' }), []);
  assert.deepEqual(admittedStructures({ OPTION_STRUCTURES_REAL: 'debit_vertical' }), ['debit_vertical']);
  assert.deepEqual(admittedStructures({ OPTION_STRUCTURES_REAL: 'debit_vertical, credit_vertical iron_condor,debit_vertical' }), ['debit_vertical', 'credit_vertical', 'iron_condor']);
  for (const typo of ['debit_vertical,iron_condr', 'DEBIT_VERTICAL', 'all', 'on', 'true', 'debit_vertical;credit_vertical']) {
    assert.deepEqual(admittedStructures({ OPTION_STRUCTURES_REAL: typo }), [], typo);
  }
});

test('the real account prices a multi-leg order only when its type is admitted: an open at maximum loss, a close at zero', () => {
  const vertical = OPENS[0][1];
  // With no type admitted, the refusal is the one that always stood (#187).
  for (const structures of [undefined, []]) {
    assert.match(notional('alpaca', mleg(vertical, '0.70'), { structures }).error, /Multi-leg, bracket, OCO and OTO orders/);
  }
  const admitted = ['debit_vertical'];
  const open = notional('alpaca', mleg(vertical, '0.70'), { structures: admitted });
  assert.equal(usd(open.micro), '70.00');
  assert.equal(open.structure, 'debit_vertical');
  assert.equal(open.opening, true);
  assert.equal(usd(notional('alpaca', mleg(vertical, '0.80'), { structures: admitted }).micro), '80.00');
  const close = notional('alpaca', mleg(closing(vertical), '-0.60'), { structures: admitted });
  assert.equal(close.micro, 0n);
  assert.equal(close.opening, false);
  assert.equal(notional('alpaca', mleg(OPENS[2][1], '-0.38'), { structures: admitted }).error,
    'A credit_vertical is not admitted on the real account: OPTION_STRUCTURES_REAL admits debit_vertical.');
  assert.equal(structureNotional(mleg(OPENS[2][1], '-0.38'), []).error, 'A credit_vertical is not admitted on the real account: OPTION_STRUCTURES_REAL admits none.');
  // Every shape rule still holds on the real account.
  assert.equal(notional('alpaca', mleg([leg(occ(580), BTO), leg(occ(581), STO, '2')], '0.10'), { structures: admitted }).error, UNCOVERED_RATIO);
  // A single-leg order is priced as before whatever is admitted.
  const single = { symbol: 'RIVN261002P00014000', qty: '1', side: 'buy', type: 'limit', limit_price: '0.14', position_intent: BTO, time_in_force: 'day' };
  assert.equal(usd(notional('alpaca', single, { structures: admitted }).micro), '14.00');
  assert.match(notional('alpaca', { ...single, side: 'sell', position_intent: STO }, { structures: admitted }).error, /long premium only/);
});

test('the practice account passes the House\'s stock, crypto and single-leg long option orders exactly as before', () => {
  // The bodies ltcm/adapters/alpaca.py `submit` sends.
  const house = extra => ({ qty: '1', side: 'buy', type: 'market', time_in_force: 'day', client_order_id: 'oi-7', ...extra });
  for (const body of [
    house({ symbol: 'SPY', qty: '0.04' }),
    house({ symbol: 'IWM', qty: '3', type: 'limit', limit_price: '24.95' }),
    house({ symbol: 'BRK.B', qty: '0.02', type: 'limit', limit_price: '480' }),
    house({ symbol: 'LTC/USD', qty: '0.1923', type: 'limit', limit_price: '62.39', time_in_force: 'gtc' }),
    house({ symbol: '1INCH/USD', qty: '10', time_in_force: 'gtc' }),
    house({ symbol: 'AAPL', side: 'sell', qty: '400' }),
    house({ symbol: 'RIVN261002P00014000', type: 'limit', limit_price: '0.14', position_intent: BTO }),
    house({ symbol: 'RIVN261002P00014000', side: 'sell', type: 'limit', limit_price: '0.20', position_intent: STC }),
    // Buying back a short leg alone only takes risk off (the book's repair of an unmatched short leg).
    house({ symbol: occ(580, 'P'), type: 'limit', limit_price: '0.30', position_intent: BTC }),
    // Shapes the practice account took before and that are no option: it still takes them.
    house({ symbol: 'AAPL', order_class: 'bracket', take_profit: { limit_price: '250' }, stop_loss: { stop_price: '200' } }),
    house({ symbol: 'AAPL', type: 'trailing_stop', trail_percent: '5' }),
  ]) assert.equal(practiceOrderError(body), null, JSON.stringify(body));
  // Every structure type passes, open and closed, unmetered.
  for (const [type, legs, limit] of OPENS) {
    assert.equal(practiceOrderError(mleg(legs, limit)), null, type);
    assert.equal(practiceOrderError(mleg(legs, limit, { qty: '40' })), null, `${type}: practice has no cap`);
  }
});

test('the practice check cannot be walked around by spelling, padding or an asset id', () => {
  const naked = { symbol: occ(580, 'P'), qty: '1', side: 'sell', type: 'limit', limit_price: '0.25', time_in_force: 'day', position_intent: STO };
  for (const symbol of [occ(580, 'P').toLowerCase(), 'SPY   260928P00580000', ` ${occ(580, 'P')}\n`, 'XYZ1260928P00005000',
    `${occ(580, 'P')}\u200b`, 'SPY 260928 P 00580000', 'SPY-260928-P-00580000']) {
    assert.match(practiceOrderError({ ...naked, symbol }) ?? '', /naked short/, JSON.stringify(symbol));
  }
  for (const symbol of ['904837e3-3b76-47ec-b432-046db621571b', '904837e33b7647ecb432046db621571b', '{904837e3-3b76-47ec-b432-046db621571b}',
    'urn:uuid:904837e3-3b76-47ec-b432-046db621571b', ' 904837E3-3B76-47EC-B432-046DB621571B ']) {
    assert.match(practiceOrderError({ ...naked, symbol }) ?? '', /asset id/, symbol);
  }
  const { position_intent: _, ...stock } = { ...naked, symbol: 'SPY' };
  for (const extra of [
    { Legs: [leg(occ(580, 'P'), STO)], order_class: 'mleg' },
    { 'legſ': [leg(occ(580, 'P'), STO)] },   // U+017F folds to "s" in Go's encoding/json
    { SYMBOL: occ(580, 'P'), position_intent: STO },
    { Position_Intent: STO },
    { ORDER_CLASS: 'mleg' },
    { Side: 'sell' },
  ]) assert.match(practiceOrderError({ ...stock, ...extra }) ?? '', /not in the venue's own spelling/, JSON.stringify(Object.keys(extra)));
  for (const body of [null, [], 'x', 3]) assert.equal(practiceOrderError(body), 'An order body must be a JSON object.');
});
