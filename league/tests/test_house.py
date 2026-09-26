"""The options supervisor remains responsive while workers run and preserves exit routing."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from league.house import House, Settings, REPEAT_WARNINGS
from league.tests.fakes import Clock

class HouseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.house = House(self.root, clock=self.clock)
    def tearDown(self):
        self.house.close(wait=None)
        self.tmp.cleanup()

class Supervisor(HouseCase):
    def test_empty_root_ticks_with_only_options_steps_and_verifiable_ledger(self):
        result = self.house.tick()
        health = json.loads((self.root/'health.json').read_text())
        self.assertEqual(health['pluggable_steps'], {'options_live':False,'swarm':False})
        self.assertEqual(result['budget'],'open')
        self.assertTrue(self.house.ledger.verify() > 0)
        before = self.house.ledger.head()[0]
        self.house.tick()
        self.assertGreater(self.house.ledger.head()[0], before, 'idle ticks still advance the watchdog heartbeat')
        self.assertFalse((self.root/'campaigns.sqlite').exists())

    def test_pause_stop_and_shutdown_continue_to_call_exit_owner_closed_for_new_work(self):
        calls=[]
        self.house.options_live=SimpleNamespace(tick=lambda house,**kw:calls.append(kw['open_for_business']))
        self.house.tick()
        (self.root/'PAUSE').write_text('maintenance')
        self.house.tick()
        (self.root/'PAUSE').unlink()
        (self.root/'STOP').touch()
        self.house.tick()
        (self.root/'STOP').unlink()
        self.house.begin_close();self.house.tick()
        self.assertEqual(calls,[True,False,False,False])

    def test_duplicate_background_work_is_not_queued_and_tick_does_not_wait(self):
        started,release=threading.Event(),threading.Event()
        def job():started.set();release.wait(5)
        try:
            self.assertTrue(self.house._background('backup:daily',job))
            self.assertTrue(started.wait(1))
            self.assertFalse(self.house._background('backup:daily',job))
            self.house.tick()
            health=json.loads((self.root/'health.json').read_text())
            self.assertEqual(health['background_jobs'][0]['key'],'backup:daily')
        finally:release.set();self.house.wait(timeout=2)

    def test_repeating_warning_keeps_its_original_start_across_restart(self):
        for n in range(REPEAT_WARNINGS):
            self.house.alert('warning',f'connection {n} failed')
            self.clock.advance(1)
        first=self.house._repeating_health()[0]['first_seen']
        self.house.close()
        self.house=House(self.root,clock=self.clock)
        self.house.alert('warning','connection 99 failed')
        self.assertEqual(self.house._repeating_health()[0]['first_seen'],first)

    def test_failed_plugin_leaves_warning_and_other_plugin_running(self):
        def fail(*args,**kwargs):raise ValueError('broken')
        good=[]
        self.house.options_live=SimpleNamespace(tick=fail)
        self.house.swarm=SimpleNamespace(tick=lambda *a,**kw:good.append(True))
        self.house.tick()
        self.assertEqual(good,[True])
        self.assertIn('options_live',self.house.ledger.last('ops.alert').payload['text'])
