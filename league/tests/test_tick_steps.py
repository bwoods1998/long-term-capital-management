"""Timing uses a monotonic clock; health retains slow steps and background lane timing."""
import json
from types import SimpleNamespace
from unittest.mock import patch
from league.tests.test_house import HouseCase

class TheTickSteps(HouseCase):
    def test_plugin_is_timed_and_rolls_out_of_the_hour(self):
        ticks=[0.0]
        def perf():ticks[0]+=.01;return ticks[0]
        def slow(*a,**kw):ticks[0]+=3
        self.house.options_live=SimpleNamespace(tick=slow)
        with patch('league.house.time.perf_counter',side_effect=perf):self.house.tick()
        row=json.loads((self.root/'health.json').read_text())['tick_steps']
        self.assertGreater(row['last']['steps']['options_live'],3)
        self.assertEqual(row['slowest_hour'][0]['step'],'options_live')
        self.clock.advance(3601)
        self.house.options_live.tick=lambda *a,**kw:None
        with patch('league.house.time.perf_counter',side_effect=perf):self.house.tick()
        row=json.loads((self.root/'health.json').read_text())['tick_steps']
        self.assertEqual(row['ticks_in_hour'],1)
        self.assertLess(row['last']['steps']['options_live'],1)
