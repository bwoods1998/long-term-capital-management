// Structure fixtures for the gateway's multi-leg tests (Sept 25, 2026): OCC symbols, legs and
// orders written as Alpaca's multi-leg orders are documented
// (https://docs.alpaca.markets/docs/options-level-3-trading) and as `league/structures.py`
// `mleg_legs` writes them, and one opening order of every type in the structure spec.

/** An OCC symbol: SPY, the Sept 28 expiry unless named, the strike in dollars. */
export const occ = (strike, right = 'C', expiry = '260928', root = 'SPY') =>
  `${root}${expiry}${right}${String(Math.round(strike * 1000)).padStart(8, '0')}`;
/** One leg as Alpaca's documented `legs` rows are written (and `structures.mleg_legs` writes them). */
export const leg = (symbol, intent, ratio = '1') => ({
  symbol, ratio_qty: ratio, side: intent.startsWith('buy') ? 'buy' : 'sell', position_intent: intent,
});
/** A multi-leg order as the practice adapter sends one. */
export const mleg = (legs, limit, extra = {}) => ({
  order_class: 'mleg', qty: '1', type: 'limit', limit_price: limit, time_in_force: 'day', legs, client_order_id: 'oi-s1', ...extra,
});
export const BTO = 'buy_to_open';
export const STO = 'sell_to_open';
export const STC = 'sell_to_close';
export const BTC = 'buy_to_close';
/** The same legs, closing: a long leg sold to close, a short leg bought to close. */
export const closing = legs => legs.map(row => leg(row.symbol, row.position_intent === BTO ? STC : BTC, row.ratio_qty));

// Every type of the spec, opened, as the House would send it: [type, legs, signed limit, max loss $].
export const OPENS = [
  ['debit_vertical', [leg(occ(580), BTO), leg(occ(581), STO)], '0.55', '55.00'],
  ['debit_vertical', [leg(occ(581, 'P'), BTO), leg(occ(580, 'P'), STO)], '0.45', '45.00'],
  ['credit_vertical', [leg(occ(590), STO), leg(occ(591), BTO)], '-0.38', '62.00'],
  ['credit_vertical', [leg(occ(581, 'P'), STO), leg(occ(580, 'P'), BTO)], '-0.30', '70.00'],
  ['iron_condor', [leg(occ(579, 'P'), BTO), leg(occ(580, 'P'), STO), leg(occ(590), STO), leg(occ(591), BTO)], '-0.38', '62.00'],
  ['iron_butterfly', [leg(occ(584, 'P'), BTO), leg(occ(585, 'P'), STO), leg(occ(585), STO), leg(occ(587), BTO)], '-1.40', '60.00'],
  ['long_butterfly', [leg(occ(580), BTO), leg(occ(581), STO, '2'), leg(occ(582), BTO)], '0.20', '20.00'],
  ['long_butterfly', [leg(occ(586, 'P'), BTO), leg(occ(584, 'P'), STO, '2'), leg(occ(582, 'P'), BTO)], '0.35', '35.00'],
  ['calendar', [leg(occ(585, 'C', '260928'), STO), leg(occ(585, 'C', '261002'), BTO)], '0.40', '40.00'],
  ['diagonal', [leg(occ(586, 'C', '260928'), STO), leg(occ(585, 'C', '261002'), BTO)], '0.90', '90.00'],
  ['diagonal', [leg(occ(584, 'P', '260928'), STO), leg(occ(585, 'P', '261002'), BTO)], '0.95', '95.00'],
  ['long_straddle', [leg(occ(585), BTO), leg(occ(585, 'P'), BTO)], '3.10', '310.00'],
  ['long_strangle', [leg(occ(590), BTO), leg(occ(580, 'P'), BTO)], '0.90', '90.00'],
];
