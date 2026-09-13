"""Public presentation only receives measured fields, never private model prose."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from scripts import export_presentation as export


class PresentationExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'private.sqlite'
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE secret (value TEXT)')
            db.execute("INSERT INTO secret VALUES ('DO_NOT_PUBLISH')")
        self.status = {'saved_at':'2026-09-13T07:15:04Z','state':'complete',
            'submitted_requests':2,'estimated_usd':'0.25','unknown_requests':0,'source_documents':12,
            'companies':[{'symbol':'NVDA','completed_steps':9,'baseline_checks':{'valid':False,'private':'DO_NOT_PUBLISH'},'revised_checks':{'valid':True},'judge_preferences':['revision'],'draft':'DO_NOT_PUBLISH'}]}
        self.metrics = {'models':{'test':{'requests':2,'estimated_usd':'0.25'}},'supercache':{'observed_reused_tokens':123},'sailbox':{'verified_companies':1,'persistence_verified':True,'finished':True,'private':'DO_NOT_PUBLISH'}}
        for target,name,value in [(export,'ROOT',self.root)]:
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
        for name,value in [('status',self.status),('sail_metrics',self.metrics)]:
            p=patch.object(export.overnight,name,return_value=value);p.start();self.addCleanup(p.stop)

    def test_only_allowlisted_fields_are_exported_without_mutating_source(self):
        before=self.database.read_bytes()
        result=export.project(self.database,'test')
        self.assertEqual(before,self.database.read_bytes())
        self.assertNotIn('DO_NOT_PUBLISH',json.dumps(result))
        self.assertEqual(result['companies'][0]['revised_check'],True)
        self.assertFalse(result['trace_recorded'])
        self.assertEqual(result['known_inference_usd'],'0.25')

    def test_measurement_disagreement_blocks_export(self):
        for field,value in [('requests',3),('estimated_usd','0.26')]:
            metrics=deepcopy(self.metrics);metrics['models']['test'][field]=value
            with patch.object(export.overnight,'sail_metrics',return_value=metrics):
                with self.assertRaisesRegex(ValueError,'disagree'):export.project(self.database,'test')

    def test_trace_identity_and_confirmation_are_required_and_private(self):
        digest=hashlib.sha256(b'overnight:test').hexdigest()
        path=self.root/'.data/voyages'/f'{digest}.json';path.parent.mkdir(parents=True)
        for identity,confirmed,expected in [(digest,False,False),('wrong',True,False),(digest,True,True)]:
            path.write_text(json.dumps({'workflow_sha256':identity,'delivery_confirmed':confirmed,'voyage_id':'private_trace_identifier'}))
            result=export.project(self.database,'test')
            self.assertEqual(result['trace_recorded'],expected)
            self.assertNotIn('private_trace_identifier',json.dumps(result))
