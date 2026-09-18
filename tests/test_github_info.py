"""Release-Dateiauswahl und fehlerhafte Metadaten prüfen."""
import unittest
from lotto45.github_info import parse_release

class GitHubInfoTests(unittest.TestCase):
    def fixture(self):
        return {'tag_name':'v1.0.23','published_at':'2026-09-18T12:00:00Z',
                'assets':[{'name':'other.zip','size':3,'state':'uploaded'},
                          {'name':'lotto-datenbank.zip','size':1048576,'state':'uploaded'}]}
    def test_database_asset_selected(self):
        data=parse_release(self.fixture())
        self.assertEqual(data['name'],'lotto-datenbank.zip')
        self.assertTrue(data['size'].startswith('1.00 MiB'))
        self.assertEqual(data['version'],'v1.0.23')
    def test_missing_incomplete_or_invalid_asset(self):
        for change in ('missing','uploading','size','date'):
            data=self.fixture()
            if change=='missing':data['assets']=[]
            if change=='uploading':data['assets'][1]['state']='new'
            if change=='size':data['assets'][1]['size']=-1
            if change=='date':data['published_at']='invalid'
            with self.subTest(change=change),self.assertRaises((ValueError,StopIteration)):
                parse_release(data)
