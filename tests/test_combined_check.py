"""Gemeinsamer Prüfablauf: Bericht auch bei Teilfehlern, Abbruch und Schreibschutz."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,tempfile,threading,unittest
from lotto45.database import connect
from lotto45.services import update_check_report

class CombinedCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'db.sqlite3'
        with closing(connect(self.db)):pass
    def run_check(self,**kwargs):
        return update_check_report(self.db,[],self.root/'logs',**kwargs)
    @patch('lotto45.archive_download.download_selected',return_value={'files':[], 'errors':[]})
    def test_success(self,download):
        events=[];r=self.run_check(progress=lambda event,value:events.append((event,value)))
        self.assertTrue(r['database_ok']);self.assertFalse(r['errors'])
        report=json.loads(Path(r['report_path']).read_text())
        self.assertEqual(report['integrity'],['ok']);self.assertEqual(report['workflow'],dict.fromkeys(['probe_sources','check_data','db_check','diagnose'],'ok'))
        self.assertNotIn(str(self.root),json.dumps(report))
        self.assertEqual([value for event,value in events if event=='phase'],['probe_sources','check_data','db_check','diagnose'])
    @patch('lotto45.archive_download.download_selected',side_effect=OSError('offline'))
    def test_download_error_still_checks_and_reports(self,download):
        r=self.run_check();self.assertTrue(r['database_ok']);self.assertEqual(len(r['errors']),1)
        self.assertTrue(Path(r['report_path']).exists())
    @patch('lotto45.services.check',side_effect=ValueError('L011: bad database'))
    @patch('lotto45.archive_download.download_selected',return_value={'files':[], 'errors':[]})
    def test_integrity_error_reported(self,download,check):
        r=self.run_check();self.assertFalse(r['database_ok']);self.assertTrue(r['errors'])
        self.assertTrue(Path(r['report_path']).exists())
    @patch('lotto45.archive_download.download_selected')
    def test_cancel_stops(self,download):
        cancel=threading.Event();cancel.set()
        with self.assertRaises(InterruptedError):self.run_check(cancel=cancel)
        download.assert_not_called();self.assertFalse((self.root/'logs').exists())
    @patch('lotto45.archive_download.download_selected',return_value={'files':[], 'errors':[]})
    def test_report_write_error_visible(self,download):
        (self.root/'logs').write_text('blocked')
        r=self.run_check();self.assertIsNone(r['report_path']);self.assertIn('L001',r['errors'][-1]['message'])

    @patch('lotto45.archive_download.probe_sources',return_value=[{'name':'Archive','status':'L008: offline','records':0}])
    @patch('lotto45.archive_download.download_selected',return_value={'files':[], 'errors':[]})
    def test_source_error_still_runs_remaining_steps(self,download,probe):
        r=self.run_check();self.assertEqual(r['stages']['probe_sources'],'errors')
        self.assertTrue(r['database_ok']);download.assert_called_once()
        report=json.loads(Path(r['report_path']).read_text())
        self.assertEqual(report['source_checks'][0]['status'],'L008')
        self.assertTrue(r['errors'])
