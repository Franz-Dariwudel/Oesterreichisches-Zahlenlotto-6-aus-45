"""Quellenauswahl und Netzwerk-/Importablauf mit isolierten Dateien prüfen."""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lotto45.archive_download import (DEFAULT_SOURCES, discover_archives, download_selected,
    load_sources, save_sources, validate_url)
from lotto45.database import connect


class SourceDownloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root/'Downloads'
        self.folder.mkdir()
        (self.folder/'keep.txt').write_text('existing download')
        self.db = self.root/'archive.sqlite3'
        self.record = {'spiel': 'joker', 'datum': '2026-09-13', 'nummer': '001234'}
        self.page = 'https://example.org/archive/'
        self.data = 'https://example.org/archive/draws.json'
        self.requests = []
        self.responses = {self.page: b'<html><a href="draws.json">draws</a></html>',
                          self.data: json.dumps([self.record]).encode()}

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self, url):
        self.requests.append(url)
        return self.responses[url]

    def source(self, url=None, enabled=True):
        return {'name': 'Test', 'url': url or self.page, 'enabled': enabled}

    def assert_clean(self):
        self.assertEqual([p.name for p in self.folder.iterdir()], ['keep.txt'])

    def test_selection_persistence_and_existing_settings(self):
        (self.root/'config').mkdir()
        (self.root/'config/settings.json').write_text('{"language":"en"}')
        sources = [self.source(), self.source('https://example.org/disabled', False)]
        save_sources(sources, self.root)
        self.assertEqual(load_sources(self.root), sources)
        self.assertEqual(json.loads((self.root/'config/settings.json').read_text()), {'language':'en'})
        self.assertEqual(load_sources(self.root/'new'), DEFAULT_SOURCES)
        save_sources([], self.root)
        self.assertEqual(load_sources(self.root), [])

    def test_bad_sources_do_not_replace_file(self):
        save_sources([self.source()], self.root)
        for sources in [[self.source(),self.source()], [self.source('file:///tmp/archive')], [{'name':'bad'}]]:
            with self.assertRaises(ValueError): save_sources(sources, self.root)
            self.assertEqual(load_sources(self.root), [self.source()])
        for url in ['https://','https://user:password@example.org/x','https://example.org:bad','https://example.org/a\nb']:
            with self.assertRaises(ValueError): validate_url(url)

    def test_only_selected_sources_import_and_reimport(self):
        sources = [self.source(), self.source('https://example.org/disabled', False)]
        first = download_selected(sources, self.db, self.folder, self.fetch)
        self.assertFalse(first['errors'])
        self.assertEqual(len(first['files']), 1)
        self.assertEqual(self.requests, [self.page,self.data])
        with closing(connect(self.db)) as con:
            self.assertEqual(con.execute('SELECT nummer FROM joker_ziehungen').fetchone()[0], '001234')
        second = download_selected(sources, self.db, self.folder, self.fetch)
        self.assertTrue(second['files'][0]['bereits_importiert'])
        with closing(connect(self.db)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM joker_ziehungen').fetchone()[0], 1)
        self.assert_clean()

    def test_new_draw_in_updated_source_is_added_once(self):
        selected=[self.source()]
        download_selected(selected,self.db,self.folder,self.fetch)
        new={**self.record,'datum':'2026-09-16','nummer':'123456'}
        self.responses[self.data]=json.dumps([self.record,new]).encode()
        updated=download_selected(selected,self.db,self.folder,self.fetch)
        self.assertFalse(updated['errors'])
        self.assertEqual(updated['files'][0]['aenderungen'],1)
        download_selected(selected,self.db,self.folder,self.fetch)
        with closing(connect(self.db,create=False)) as con:
            self.assertEqual([tuple(r) for r in con.execute('SELECT datum,nummer FROM joker_ziehungen ORDER BY datum')],
                             [('2026-09-13','001234'),('2026-09-16','123456')])
        self.assert_clean()

    def test_deselect_all_makes_no_requests(self):
        with self.assertRaises(ValueError): download_selected([self.source(enabled=False)],self.db,self.folder,self.fetch)
        self.assertEqual(self.requests, [])
        self.assertFalse(self.db.exists())
        self.assert_clean()

    def test_relative_links_csv_preference_and_ignored_links(self):
        raw=b'''<a href="NN_W2D_STAT_Joker_2026.pdf">PDF</a>
        <a href="NN_W2D_STAT_Joker_2026.csv?v=1&amp;x=2">CSV</a>
        <a href="NN_W2D_STAT_Joker_2026.csv?v=2">duplicate</a>
        <a href="javascript:bad()">ignored</a><a href="setup.sh">ignored</a>'''
        self.assertEqual(discover_archives(raw,self.page), [self.page+'NN_W2D_STAT_Joker_2026.csv?v=1&x=2'])

    def test_failure_is_reported_and_other_source_imported(self):
        sources = [self.source('https://example.org/offline'),self.source()]
        result = download_selected(sources,self.db,self.folder,self.fetch)
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(len(result['files']),1)
        self.assert_clean()

    def test_wrong_content_is_not_imported(self):
        self.responses[self.data] = b'<html>not json</html>'
        result = download_selected([self.source()],self.db,self.folder,self.fetch)
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(result['files'],[])
        with closing(connect(self.db)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM import_quellen').fetchone()[0],0)
        self.assert_clean()

    def test_unsupported_page_visible_failure(self):
        self.responses[self.page] = b'<html>No archives here</html>'
        result = download_selected([self.source()],self.db,self.folder,self.fetch)
        self.assertEqual(len(result['errors']),1)
        self.assertFalse(result['files'])
        self.assert_clean()

    def test_direct_json_and_atomic_validation(self):
        self.responses[self.data] = json.dumps([self.record,{**self.record,'datum':'2026-09-14','nummer':'invalid'}]).encode()
        result = download_selected([self.source(self.data)],self.db,self.folder,self.fetch)
        self.assertEqual(len(result['errors']),1)
        with closing(connect(self.db)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM joker_ziehungen').fetchone()[0],0)
        self.assert_clean()

    def test_failed_staging_cleans_up(self):
        with patch.object(Path,'write_bytes',side_effect=PermissionError('write blocked')):
            result = download_selected([self.source()],self.db,self.folder,self.fetch)
        self.assertEqual(len(result['errors']),1)
        self.assertFalse(result['files'])
        self.assert_clean()

    def test_known_source_conflict_preserves_draw(self):
        download_selected([self.source()],self.db,self.folder,self.fetch)
        self.responses[self.data]=json.dumps([{**self.record,'nummer':'999999'}]).encode()
        result=download_selected([self.source()],self.db,self.folder,self.fetch)
        self.assertFalse(result['errors'])
        self.assertEqual(result['files'][0]['konflikte'],1)
        with closing(connect(self.db)) as con:
            self.assertEqual(con.execute('SELECT nummer FROM joker_ziehungen').fetchone()[0],'001234')
            self.assertEqual(con.execute('SELECT count(*) FROM import_quellen').fetchone()[0],2)
        self.assert_clean()


if __name__=='__main__': unittest.main()
