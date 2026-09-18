"""Zusätzliche Zahlenquelle darf vorhandene Quoten und Reihenfolgen nicht löschen."""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from lotto45.archive_download import parse_archive,download_selected
from lotto45.database import connect,ingest

HEADER=b'date,n1,n2,n3,n4,n5,n6,zusatzzahl\n'

class SimpleArchiveTest(unittest.TestCase):
    def test_detect_format_and_validate_every_row(self):
        raw=HEADER+b'2026-09-13,2,7,11,16,34,42,36\n'
        records,issues=parse_archive(raw,'results.csv')
        self.assertFalse(issues);self.assertEqual(records[0]['zahlen'],[2,7,11,16,34,42]);self.assertNotIn('quoten',records[0])
        for bad in [b'wrong,header\n',HEADER,HEADER+b'2026-09-13,2,2,11,16,34,42,36\n',
                    HEADER+b'2026-09-13,2,7,11,16,34,42,42\n',HEADER+b'2026-09-13,2,7,11,16,34,42\n',raw+raw.splitlines()[1]+b'\n']:
            with self.assertRaises(ValueError):parse_archive(bad,'results.csv')

    def test_download_preserves_existing_quotes_order_and_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);db=temp/'db';folder=temp/'Downloads';folder.mkdir();(folder/'keep').write_text('keep')
            with closing(connect(db)) as con:
                record={'spiel':'lotto','datum':'2026-09-13','zahlen':[2,7,11,16,34,42],'zusatzzahl':36,
                        'reihenfolge':[42,34,16,11,7,2],
                        'quoten':[{'klasse':'6er','gewinner':3,'betrag_hundertstel':12300,'waehrung':'EUR','betrag_art':'je_gewinn'}]}
                ingest(con,b'official','official',[record]);original=con.execute('SELECT * FROM lotto_quoten').fetchall()
            raw=HEADER+b'2026-09-13,2,7,11,16,34,42,36\n'
            source={'name':'GitHub','url':'https://example.org/results.csv','enabled':True}
            result=download_selected([source],db,folder,fetch=lambda _:raw)
            self.assertFalse(result['errors'])
            with closing(connect(db)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM lotto_ziehungen').fetchone()[0],1)
                self.assertEqual([tuple(r) for r in con.execute('SELECT * FROM lotto_quoten')],[tuple(r) for r in original])
                self.assertEqual([r[0] for r in con.execute('SELECT zahl FROM lotto_ziehungszahlen ORDER BY position')],[42,34,16,11,7,2])
                self.assertEqual(con.execute('SELECT count(*) FROM import_quellen').fetchone()[0],2)
            self.assertEqual([p.name for p in folder.iterdir()],['keep'])
