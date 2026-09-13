import hashlib,json,signal,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch, call
from portfolio_runtime import supervisor_guest as g
class BackupTests(unittest.TestCase):
 def test_snapshots_are_checked_and_manifest_committed_after_artifacts(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'config').mkdir();(root/'state').mkdir()
   (root/'config/run.json').write_text(json.dumps({'service_id':'week-20260914','backup_url':'https://portfolio-supervisor.example.workers.dev/v1/backups'}))
   (root/'host-manifest.json').write_text('{}')
   with closing(sqlite3.connect(root/'state/paper.sqlite')) as db, db:db.execute('create table events(id integer primary key,value text)');db.execute("insert into events(value)values('saved')")
   (root/'state/credentials.env').write_text('secret must not be copied')
   (root/'state/raw').mkdir();(root/'state/raw/not-backed-up.json').write_text('{}')
   rows=[]
   def uploader(url,path,h):
    data=path.read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),h);rows.append((url,data))
   result=g.backup(root,uploader=uploader)
   self.assertEqual(result['status'],'complete');self.assertTrue(rows[-1][0].endswith('.json'))
   manifest=json.loads(rows[-1][1]);names={x['path'] for x in manifest['files']}
   self.assertIn('state/paper.sqlite',names);self.assertNotIn('state/credentials.env',names);self.assertNotIn('state/raw/not-backed-up.json',names)
   self.assertFalse(manifest['consistent_across_databases'])
 def test_failed_upload_does_not_claim_a_completed_snapshot(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'config').mkdir();(root/'state').mkdir()
   (root/'config/run.json').write_text(json.dumps({'service_id':'week-20260914','backup_url':'https://portfolio-supervisor.example.workers.dev/v1/backups'}))
   (root/'host-manifest.json').write_text('{}')
   def failing(*args):raise OSError('network')
   with self.assertRaises(OSError):g.backup(root,uploader=failing)
   state=json.loads((root/'state/backup-health.json').read_text());self.assertEqual(state['status'],'failed');self.assertNotIn('manifest_key',state)
class ForceStopTests(unittest.TestCase):
 def test_only_verified_bootstrap_and_its_exact_service_child_can_be_killed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'state').mkdir();proc=root/'test-proc'
   boot=proc/'sys/kernel/random';boot.mkdir(parents=True);(boot/'boot_id').write_text('current-boot')
   def process(pid,ppid,args):
    p=proc/str(pid);p.mkdir();(p/'status').write_text(f'Name: python3\nPPid:\t{ppid}\n');(p/'cmdline').write_bytes(b'\0'.join(args)+b'\0')
   process(100,1,[b'python3',b'/workspace/host-boot.py'])
   process(101,100,[b'python3',b'-m',b'portfolio_runtime.service',b'run'])
   process(102,99,[b'python3',b'-m',b'portfolio_runtime.service',b'run'])
   process(103,100,[b'python3',b'-m',b'unrelated_service'])
   (root/'state/host-process.json').write_text(json.dumps({'pid':100,'boot_id':'current-boot'}))
   real_path=Path
   def mapped_path(value):
    value=str(value)
    return proc/value.removeprefix('/proc/').lstrip('/') if value.startswith('/proc/') else proc if value=='/proc' else real_path(value)
   with patch.object(g,'Path',side_effect=mapped_path),patch.object(g.os,'kill') as kill:
    self.assertEqual(g.force_stop(root),{'stopped':True})
    self.assertEqual(kill.call_args_list,[call(101,signal.SIGKILL),call(100,signal.SIGKILL)])

 def test_stale_boot_reserved_pid_or_changed_command_denies_before_any_signal(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'state').mkdir();proc=root/'test-proc';boot=proc/'sys/kernel/random';boot.mkdir(parents=True)
   (boot/'boot_id').write_text('current-boot');parent=proc/'100';parent.mkdir();(parent/'cmdline').write_bytes(b'python3\0unrelated.py\0')
   real_path=Path
   def mapped_path(value):
    value=str(value)
    return proc/value.removeprefix('/proc/').lstrip('/') if value.startswith('/proc/') else proc if value=='/proc' else real_path(value)
   for saved in [{'pid':1,'boot_id':'current-boot'},{'pid':True,'boot_id':'current-boot'},{'pid':100,'boot_id':'old-boot'},{'pid':100,'boot_id':'current-boot'}]:
    (root/'state/host-process.json').write_text(json.dumps(saved))
    with patch.object(g,'Path',side_effect=mapped_path),patch.object(g.os,'kill') as kill:
     with self.assertRaisesRegex(ValueError,'process_identity_changed'):g.force_stop(root)
     kill.assert_not_called()

if __name__=='__main__':unittest.main()
