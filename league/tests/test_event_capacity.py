"""First-agent capacity and shared reservations, using only disposable fake venues."""
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

from league.book import Book, Limits
from league.fees import Fees
from league.tests.fakes import FakeBroker, iso
from league.tests.test_book import BookCase, event
from league.tests.test_house import BUYER, HouseCase


class EventCapital(BookCase):
    venue, family, real, cash = 'kalshi', 'kalshi', True, '500'

    def setup_first(self, budget=None):
        self.book.reconcile()
        self.seat('first', usd='25', position='10', order='10')
        self.broker.set_quote(event(), '.49', '.50')
        if budget is not None:
            self.book.event_capital_budget = lambda: D(budget)

    def test_authorized_reserve_fixes_first_agent_denominator_without_raising_its_stake(self):
        self.setup_first()
        buy = self.intent('first', event(), 'buy', '12')  # $6 principal
        quote = self.broker.quote(event())
        self.assertTrue(any('cap 2.50' in r for r in self.book.check(buy, quote, iso(self.clock))))
        self.book.event_capital_budget = lambda: D('500')
        self.assertEqual(self.book.check(buy, quote, iso(self.clock)), [])
        too_large = self.intent('first', event(), 'buy', '18')
        self.assertTrue(any('cap 7.50' in r for r in self.book.check(too_large, quote, iso(self.clock))))
        self.assertEqual(self.book.account('first').staked, D(25))
        risk = self.book.event_risk('first', [event().market_id])
        self.assertEqual(risk['basis'], 'authorized_venue')
        self.assertEqual((risk['capital_usd'], risk['floor_market_cap_usd'], risk['floor_cluster_cap_usd']), (500, 50, 125))
        self.assertEqual(risk['remaining_by_market_usd'][event().market_id], 7.5)
        self.assertEqual(self.broker.submitted, [], 'a capacity check never places a trade')

    def test_losses_survive_sweep_restart_and_later_deposit(self):
        self.setup_first('100')
        self.book.submit([self.intent('first', event(), 'buy', '12')])
        self.book.settle(event().market_id, 'no')
        loss = self.book.equity('first') - D(25)
        self.assertLess(loss, -D(6))  # fees count too
        expected = D(100) + loss
        self.assertEqual(self.book.event_floor_capital(), expected)
        self.book.stake('first', -self.book.account('first').cash, note='account closed')
        self.book = self.new_book()
        self.book.event_capital_budget = lambda: D(100)
        self.assertEqual(self.book.event_floor_capital(), expected)
        self.book.baseline_cash += D(1000)  # even a subsequently reconciled deposit cannot enlarge the grant
        self.assertEqual(self.book.event_floor_capital(), expected)

    def test_funding_and_profit_cannot_enlarge_the_envelope(self):
        self.setup_first('1000')
        self.assertEqual(self.book.event_floor_capital(), D(500), 'only $500 actually funded')
        self.book.event_capital_budget = lambda: D(100)
        self.book.account('first').cash += D(10)
        self.assertEqual(self.book.event_floor_capital(), D(100))
        self.book.baseline_cash = None
        self.assertEqual(self.book.event_floor_capital(), D(0))

    def test_other_agents_working_buys_consume_the_same_visible_headroom(self):
        self.setup_first('100')
        self.seat('second', usd='25', position='10', order='10')
        self.broker.set_quote(event(), '.49', '.51')
        result = self.book.submit([self.intent('first', event(), 'buy', '12', order_type='limit', limit_price='.50', post_only=True)])[0]
        self.assertEqual(result.status, 'resting')
        risk = self.book.event_risk('second', [event().market_id])
        self.assertEqual(risk['remaining_by_market_usd'][event().market_id], 4)
        buy = self.intent('second', event(), 'buy', '10', order_type='limit', limit_price='.50')
        self.assertTrue(any('across the live desks' in r for r in self.book.check(buy, self.broker.quote(event()), iso(self.clock))))
        own = self.book.event_risk('first', [event().market_id])
        self.assertEqual(own['remaining_by_market_usd'][event().market_id], 1.5)

    def test_same_batch_reserves_correlated_markets_against_authorized_capital(self):
        self.setup_first('40')
        self.book.rules['max_event_market_floor_pct'] = '0'  # isolate the cluster rule
        self.seat('second', usd='25', position='10', order='10')
        other = event(ticker='KXETHD-26SEP2017-T4999')
        self.broker.set_quote(other, '.49', '.50')
        first = self.intent('first', event(), 'buy', '12')
        second = self.intent('second', other, 'buy', '12')
        reasons = self.book.check(second, self.broker.quote(other), iso(self.clock), pending=[(first, self.broker.quote(event()))])
        self.assertTrue(any('cap 10.00' in r and 'settle together' in r for r in reasons), reasons)

    def test_zero_capital_blocks_entries_but_never_blocks_a_reducing_exit(self):
        self.setup_first('100')
        self.book.submit([self.intent('first', event(), 'buy', '10')])
        self.book.event_capital_budget = lambda: D(0)
        quote = self.broker.quote(event())
        reasons = self.book.check(self.intent('first', event(), 'buy', '1'), quote, iso(self.clock))
        self.assertTrue(any('no funded authorized' in r for r in reasons))
        self.assertEqual(self.book.check(self.intent('first', event(), 'sell', '10'), quote, iso(self.clock)), [])

    def test_larger_concentration_basis_does_not_dilute_daily_loss_stop(self):
        self.setup_first('500')
        buy = self.intent('first', event(), 'buy', '1')
        quote = self.broker.quote(event())
        self.assertEqual(self.book.check(buy, quote, iso(self.clock)), [])
        self.book.account('first').cash -= D(3)
        reasons = self.book.check(buy, quote, iso(self.clock))
        self.assertTrue(any('floor daily loss' in r for r in reasons), reasons)


class EventSnapshot(HouseCase):
    def test_strategy_and_research_preview_see_effective_caps_and_owned_refusals(self):
        code = BUYER.replace('"venue": "alpaca"', '"venue": "kalshi", "series": ["KXBTCD"]')
        agent = self.house.spawn('kalshi-test', 'test', code)
        broker = FakeBroker('kalshi', family='kalshi', cash='517.75')
        self.house.campaigns = SimpleNamespace(live_authorization=lambda: {'policy': {'venue_capital_usd': {'kalshi': '517.75'}}}, close=lambda: None)
        book = Book('kalshi', broker, self.house.ledger, fees=Fees('kalshi'), real_money=True, clock=self.clock,
                    event_capital_budget=lambda: self.house._event_capital_budget('kalshi'))
        book.reconcile()
        book.limits[agent.id] = Limits(D(10), D(10))
        book.stake(agent.id, 25)
        self.house.ledger.append('book.refused', {'book': 'kalshi', 'intent_id': 'rejected-first', 'reasons': ['cap 2.50']}, agent=agent.id)
        market = {'market': event().market_id, 'volume_24h': 100}
        with patch.object(self.house, '_markets', return_value=[market]):
            ctx = self.house.snapshot(agent, book)
        self.assertEqual(ctx['limits'], {'max_order_usd': 7.5, 'max_position_usd': 7.5})
        self.assertEqual(ctx['event_risk']['capital_usd'], 517.75)
        self.assertEqual(ctx['event_risk']['remaining_by_market_usd'][event().market_id], 7.5)
        self.assertFalse(ctx['recent_order_outcomes'][0]['submitted_to_venue'])
        self.assertNotIn('event_risk', market, 'shared market cache stays independent of agent capacity')
        from league.researcher import _trim
        self.assertEqual(_trim(ctx)['event_risk'], ctx['event_risk'])
