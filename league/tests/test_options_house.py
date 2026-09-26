"""The production factory composes only live options, swarm and operator services."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from league import service
from league.live_trading import LiveGrant

NO_LIVE={'live':{'enabled':False}}
LIVE={'live':{'enabled':True,'thread':False,'require_paper_proof':True}}
CUT_PIECES=('campaigns','feeds','jev_floor','lab','hypotheses','semantic_lab','shards','kalshi_data','registry','books','economy')

def no_network(*a,**kw):raise OSError('no network in tests')

class BuildCase(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup)
        self.made=[]
    def broker(self,venue,**kw):
        self.made.append((venue,kw));return SimpleNamespace(venue=venue)
    def build(self,*,real_money=False,config=None,sail=None,repository_config=False,**kw):
        config={**service.load_config(),**LIVE,**(config or {}),'real_money':real_money}
        options=dict(research=False,publish=False,merton=False,local_sandbox=not real_money);options.update(kw)
        with patch.object(service,'load_env'),patch.object(service,'secret',return_value='t'*40), \
             patch('league.venues.gateway_broker',side_effect=self.broker),patch('urllib.request.urlopen',side_effect=no_network):
            house=service.build(Path(self.dir.name)/'state',config=config,**options)
        self.addCleanup(house.close,wait=None)
        return house

class Build(BuildCase):
    def test_retired_systems_are_not_constructed_and_grant_stays_separate(self):
        house=self.build(config=NO_LIVE,publish=True)
        for name in CUT_PIECES:self.assertIsNone(getattr(house,name,None),name)
        self.assertIsInstance(house.grant,LiveGrant)
        self.assertEqual(house.publisher.broker.venue,'alpaca')
        self.assertFalse(house.grant.allows_live(2))
        self.assertFalse((house.root/'campaigns.sqlite').exists())
    def test_market_data_always_uses_real_read_credentials_and_paper_never_trades_real(self):
        for real in (False,True):
            with self.subTest(real=real):
                house=self.build(real_money=real)
                live=house.options_live
                self.assertIsNotNone(live)
                self.assertIs(live.grant,house.grant)
                self.assertEqual(live.market.client.venue,'alpaca')
                self.assertEqual(live.paper.client.venue,'alpaca-paper')
                self.assertEqual(live.real is not None,real)
    def test_canary_has_no_secrets_or_paid_or_venue_work(self):
        with patch.object(service,'secret',side_effect=AssertionError('no secret')):
            house=self.build(canary=True,real_money=True)
        self.assertFalse(house.settings.real_money)
        self.assertIsNone(house.options_live);self.assertIsNone(house.swarm)
    def test_auto_update_requires_explicit_true(self):
        for cfg in ({},{'auto_update':False},{'auto_update':'true'}):self.assertFalse(service.auto_update(cfg))
        self.assertTrue(service.auto_update({'auto_update':True}))

    def test_deployment_canary_exercises_options_runtime_without_network_or_secrets(self):
        import contextlib
        import io
        from league.__main__ import main, verify
        from league.ledger import Ledger
        root = Path(self.dir.name) / 'isolated-canary'
        with patch.object(service, 'secret', side_effect=AssertionError('secret requested')), \
             patch.object(service, 'load_env'), \
             patch('urllib.request.urlopen', side_effect=AssertionError('network requested')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['tick', '--canary', '--root', str(root)]), 0)
        result = verify(root, canary=True)
        self.assertGreater(result['ledger_rows_verified'], 0)
        ledger = Ledger(root / 'ledger.sqlite')
        try:
            proof = ledger.last('canary.proof').payload
            self.assertTrue(proof['synthetic'])
            self.assertEqual(proof['structure_resolution'], 'ok')
        finally:
            ledger.close()
        self.assertFalse((root / 'live.sqlite').exists())
        self.assertFalse((root / 'swarm.sqlite').exists())

    def test_missing_canary_state_is_a_failure_not_a_new_empty_ledger(self):
        from league.__main__ import verify
        root = Path(self.dir.name) / 'missing'
        with self.assertRaisesRegex(RuntimeError, 'no ledger'):
            verify(root, canary=True)
        self.assertFalse(root.exists())

class Step:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def tick(self,house,*,open_for_business):
        self.calls.append(open_for_business)
        if self.fail:raise RuntimeError('a step that breaks')
        return {'ran':len(self.calls)}

class PluggableSteps(BuildCase):
    def test_plugin_order_and_summaries(self):
        house=self.build(config=NO_LIVE);house.options_live=Step();house.swarm=Step()
        result=house.tick()
        self.assertEqual(result['options_live'],{'ran':1});self.assertEqual(result['swarm'],{'ran':1})
        steps=list(house._tick_last['steps'])
        self.assertLess(steps.index('options_live'),steps.index('swarm'))
    def test_site_inputs_combine_private_component_allowlisted_views(self):
        house=self.build(config=NO_LIVE)
        house.swarm=SimpleNamespace(site_inputs=lambda:{'agents':[{'id':'f'}],'compute':{'sail_usd':'1.50'}})
        house.options_live=SimpleNamespace(site_inputs=lambda:{'structures':[{'id':'p'}],'compute':{'sail_usd':'.25'}})
        result=house.site_inputs()
        self.assertEqual(result['agents'],[{'id':'f'}]);self.assertEqual(str(result['compute']['sail_usd']),'1.75')
