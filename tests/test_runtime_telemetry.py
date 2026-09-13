from pathlib import Path
import tempfile
import unittest
from portfolio_runtime.telemetry import Voyage
from test_runtime_provider import Script


class TelemetryTests(unittest.TestCase):
    def test_restart_retries_exact_event_sequences_without_recreating_voyage(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'voyage.sqlite';config={'voyage_id':'voyage_example','key_fingerprint':'a'*64,'injected_auth':True}
            script=Script(TimeoutError(),{})
            trace=Voyage(path,config,transport=script)
            trace.event('step-1','research.completed',{'checks':2});trace.event('step-1','research.completed',{'checks':2})
            self.assertFalse(trace.flush())
            restored=Voyage(path,config,transport=script);self.assertTrue(restored.flush());self.assertEqual(script.calls[0],script.calls[1])
            self.assertEqual(script.calls[1][2]['events'][0]['sequence_id'],1_000_000)
            restored.flush();self.assertEqual(len(script.calls),2)
            self.assertEqual(trace.headers()['X-Sail-Voyage-Id'],'voyage_example')
            with self.assertRaises(ValueError):trace.event('step-1','research.completed',{'checks':3})
            with self.assertRaises(ValueError):Voyage(path,{**config,'voyage_id':'voyage_other'},transport=script)
    def test_terminal_is_explicit_and_first_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            trace=Voyage(Path(temp)/'v.sqlite',{'voyage_id':'voyage_example','key_fingerprint':'a'*64},transport=Script())
            trace.event('done','voyage.completed',{'completed':True})
            trace.event('done','voyage.completed',{'completed':True})
            with self.assertRaises(ValueError):trace.event('failed','voyage.failed')


if __name__=='__main__':unittest.main()
