"""Regressionsprüfungen auf kleinen, isolierten Datenbanken."""
import itertools,json,math,sqlite3,tempfile,unittest
from pathlib import Path
from lotto45.database import connect,tip_id,ingest
from lotto45.importers import quote,parse_lotto,parse_joker_csv
from lotto45.settings import download

class ArchiveTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.c=connect(self.root/'test.db')
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def r(self,**extra):return {'spiel':'lotto','datum':'2026-01-01','zahlen':[1,2,3,4,5,6],'zusatzzahl':7,**extra}
 def load(self,records,corrections=False):
  return ingest(self.c,json.dumps(records).encode(),'test',records,allow_corrections=corrections)
 def test_ranking(self):
  for i,ns in enumerate(itertools.islice(itertools.combinations(range(1,46),6),10000),1):self.assertEqual(tip_id(ns),i)
  self.assertEqual(tip_id([40,41,42,43,44,45]),math.comb(45,6))
 def test_idempotence_repeated_tip(self):
  self.load([self.r()]);self.load([self.r()]);self.load([self.r(datum='2026-01-02')])
  self.assertEqual(self.c.execute('SELECT count(*) FROM lotto_tipps').fetchone()[0],1)
  self.assertEqual(self.c.execute('SELECT count(*) FROM lotto_ziehungen').fetchone()[0],2)
  self.assertEqual(self.c.execute('SELECT count(*) FROM import_quellen').fetchone()[0],2)
 def test_order_preserved(self):
  order=[6,5,4,3,2,1];self.load([self.r(reihenfolge=order)]);self.load([self.r()])
  self.assertEqual([r[0] for r in self.c.execute('SELECT zahl FROM lotto_ziehungszahlen ORDER BY position')],order)
 def test_correction_audited(self):
  self.load([self.r(reihenfolge=[1,2,3,4,5,6])]);self.load([self.r(zahlen=[2,3,4,5,6,8])],True)
  self.assertEqual(self.c.execute('SELECT count(*) FROM aenderungen WHERE vorher IS NOT NULL').fetchone()[0],1)
  self.assertEqual(self.c.execute('SELECT count(*) FROM lotto_ziehungszahlen').fetchone()[0],0)
 def test_conflict_keeps_original(self):
  self.load([self.r()]);r=self.load([self.r(zusatzzahl=8)])
  self.assertEqual(r['konflikte'],1);self.assertEqual(self.c.execute('SELECT zusatzzahl FROM lotto_ziehungen').fetchone()[0],7)
 def test_invalid_import_rollback(self):
  for bad in [self.r(zusatzzahl=6),self.r(reihenfolge=[1]*6),self.r(zahlen=[1,1,2,3,4,5]),self.r(zahlen=[True,2,3,4,5,6])]:
   with self.assertRaises(ValueError):self.load([self.r(),bad])
  self.assertEqual(self.c.execute('SELECT count(*) FROM import_quellen').fetchone()[0],0)
 def test_joker_zeros(self):
  self.load([{'spiel':'joker','datum':'2026-01-01','nummer':'000012'}])
  self.assertEqual(self.c.execute('SELECT nummer FROM joker_ziehungen').fetchone()[0],'000012')
  with self.assertRaises(ValueError):self.load([{'spiel':'joker','datum':'2026-01-02','nummer':12}])
 def test_money_pool(self):
  q=quote('6er','DJP','1 .908.887,84','ATS','old');self.assertEqual(q['betrag_hundertstel'],190888784);self.assertEqual(q['betrag_art'],'jackpot')
  self.load([self.r(quoten=[q])]);self.assertEqual(self.c.execute('SELECT waehrung FROM lotto_quoten').fetchone()[0],'ATS')
  with self.assertRaises(ValueError):quote('6er','1','1,234','EUR','old')
 def test_missing_values_not_zero(self):
  q=quote('2','0','','EUR','joker');self.assertIsNone(q['betrag_hundertstel']);self.assertEqual(q['gewinner'],0)
 def test_raw_and_extras(self):
  r=self.r(foo={'unknown':'retained'});self.load([r])
  self.assertEqual(json.loads(self.c.execute('SELECT original FROM import_quellen').fetchone()[0]),[r])
  self.assertEqual(json.loads(self.c.execute('SELECT extras FROM lotto_ziehungen').fetchone()[0])['foo'],r['foo'])
 def test_fk(self):
  with self.assertRaises(sqlite3.IntegrityError):self.c.execute("INSERT INTO joker_ziehungen(datum,nummer) VALUES('2026-01-01','123456')")
 def test_joker_csv(self):
  raw='Datum;Zahl1;Zahl2;Zahl3;Zahl4;Zahl5;Zahl6;Rang 1;à;Quote;Rang 2;Rang 3;Rang 4;Rang 5;Rang 6;\nSo 04.01.;0,00;0,00;0,00;0,00;1,00;2,00;1;à;196.198,70;9;93;838;8.638;84.984;'.encode()
  rs,issues=parse_joker_csv(raw,'NN_W2D_STAT_Joker_2026.csv');self.assertFalse(issues);self.assertEqual(rs[0]['nummer'],'000012');self.assertEqual(len(rs[0]['quoten']),6)

class DownloadTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'languages').mkdir();(self.root/'languages/en.json').write_text('{"hello":"Hello"}')
  self.downloads=self.root/'Downloads';self.downloads.mkdir();(self.downloads/'keep').write_text('keep')
 def tearDown(self):self.tmp.cleanup()
 def fetch(self,url):
  if url.endswith('language-index.json'):return b'{"languages":["de","en"]}'
  if url.endswith('.json'):return b'{"hello":"Hallo","language_name":"Deutsch","language":"Sprache","save":"Speichern"}'
  return b'<html lang="de"><body>Hilfe</body></html>'
 def test_success_preservation_cleanup(self):
  self.assertEqual(download('owner/project','de',self.root,self.downloads,self.fetch),2)
  (self.root/'languages/de.json').write_text('{"hello":"Eigen"}')
  self.assertEqual(download('owner/project','de',self.root,self.downloads,self.fetch),0)
  self.assertIn('Eigen',(self.root/'languages/de.json').read_text());self.assertEqual(list(p.name for p in self.downloads.iterdir()),['keep'])
 def test_invalid_html_rolls_back(self):
  def bad(url):return b'<html lang="en"></html>' if url.endswith('.html') else self.fetch(url)
  with self.assertRaises(ValueError):download('owner/project','de',self.root,self.downloads,bad)
  self.assertFalse((self.root/'languages/de.json').exists());self.assertEqual(len(list(self.downloads.iterdir())),1)
 def test_write_failure_rolls_back(self):
  (self.root/'help').write_text('not a directory')
  with self.assertRaises(OSError):download('owner/project','de',self.root,self.downloads,self.fetch)
  self.assertFalse((self.root/'languages/de.json').exists());self.assertEqual(len(list(self.downloads.iterdir())),1)
 def test_missing_repository(self):
  with self.assertRaises(ValueError):download('','de',self.root,self.downloads,self.fetch)
 def test_network_cleanup(self):
  def bad(url):
   if url.endswith('.html'):raise OSError('offline')
   return self.fetch(url)
  with self.assertRaises(OSError):download('owner/project','de',self.root,self.downloads,bad)
  self.assertFalse((self.root/'languages/de.json').exists());self.assertEqual(len(list(self.downloads.iterdir())),1)

if __name__=='__main__':unittest.main()
