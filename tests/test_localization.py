"""Alle ausgelieferten Sprachen: Texte, Formatfelder, Hilfelinks und Dateischutz."""
from pathlib import Path
from html.parser import HTMLParser
from unittest.mock import patch
import json,re,string,tempfile,unittest
from lotto45 import settings,date_display
ROOT=Path(__file__).resolve().parents[1]
CODES=('de','en','es','fr','pt','zh','hi','ar','ru','tr')
class HelpIndex(HTMLParser):
    def __init__(self):super().__init__();self.lang=None;self.ids=[];self.links=[];self.menu=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='html':self.lang=a.get('lang')
        if 'id' in a:self.ids.append(a['id'])
        if 'data-menu' in a:self.menu.append(a['data-menu'])
        if tag=='a' and a.get('href','').startswith('#'):self.links.append(a['href'][1:])
class LocalizationTests(unittest.TestCase):
    def test_complete_catalogs_and_placeholders(self):
        catalogs=settings.catalogs(ROOT);self.assertTrue(set(CODES)<=set(catalogs))
        def fields(text):return sorted((key,spec,conv) for _,key,spec,conv in string.Formatter().parse(text) if key is not None)
        for code in CODES:
            self.assertEqual(set(catalogs[code]),set(catalogs['en']))
            for key,text in catalogs[code].items():
                with self.subTest(code=code,key=key):
                    self.assertTrue(text.strip());self.assertEqual(fields(text),fields(catalogs['en'][key]))
                    self.assertNotRegex(text,r'ZXQ|⟦\d{4}⟧')
    def test_every_help_contains_all_menu_entries_and_valid_anchors(self):
        expected=json.loads((ROOT/'resources/menu-help-index.json').read_text())['entries']
        for code in CODES:
            text=(ROOT/'help'/f'{code}.html').read_text();parser=HelpIndex();parser.feed(text)
            self.assertEqual(parser.lang,code);self.assertEqual(sorted(parser.menu),sorted(expected))
            self.assertEqual(len(parser.ids),len(set(parser.ids)))
            self.assertTrue(set(parser.links)<=set(parser.ids))
            for i in range(1,15):self.assertIn(f'L{i:03}',text)
            self.assertNotIn('start.sh',text)
    def test_download_installs_all_pairs_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'languages').mkdir();(root/'help').mkdir()
            (root/'languages/en.json').write_bytes((ROOT/'languages/en.json').read_bytes())
            downloads=root/'Downloads';downloads.mkdir();keep=downloads/'keep.txt';keep.write_text('keep')
            calls=[]
            def fetch(url):
                suffix=url.split('/main/',1)[1];calls.append(suffix);return (ROOT/suffix).read_bytes()
            for code in CODES:
                settings.download('example/project',code,root,downloads,fetch)
                self.assertTrue((root/'languages'/f'{code}.json').is_file())
                self.assertTrue((root/'help'/f'{code}.html').is_file())
            target=root/'languages/fr.json';target.write_text('{"own":"preserved"}')
            self.assertEqual(settings.download('example/project','fr',root,downloads,fetch),0)
            self.assertEqual(target.read_text(),'{"own":"preserved"}')
            self.assertEqual(list(downloads.iterdir()),[keep])
    def test_invalid_download_does_not_install_partial_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'languages').mkdir();(root/'help').mkdir()
            (root/'languages/en.json').write_bytes((ROOT/'languages/en.json').read_bytes())
            def fetch(url):
                suffix=url.split('/main/',1)[1]
                return b'<html lang="en"></html>' if suffix=='help/fr.html' else (ROOT/suffix).read_bytes()
            with self.assertRaises(ValueError):settings.download('example/project','fr',root,root/'Downloads',fetch)
            self.assertFalse((root/'languages/fr.json').exists());self.assertFalse((root/'help/fr.html').exists())
    def test_weekdays_follow_language(self):
        for code in CODES:
            with patch.object(date_display,'LANGUAGE',code):
                self.assertTrue(date_display.format_date('2026-09-18').startswith(date_display.WEEKDAYS[code][4]))
