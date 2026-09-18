"""Quoten und Prüferklärungen auf echten, unveränderten Archivtabellen prüfen."""
import json
import sqlite3
import unittest
from lotto45.database import SCHEMA,ingest
from lotto45.draw_search import parse_date_filter
from lotto45.quotes import search_quotes
from lotto45.import_review import category,read_reviews


class QuotesReviewTests(unittest.TestCase):
    def setUp(self):
        self.con=sqlite3.connect(':memory:');self.con.row_factory=sqlite3.Row
        self.con.executescript(SCHEMA);self.addCleanup(self.con.close)
        def q(rank,amount,winners=0,currency='EUR'):
            return {'klasse':rank,'regelwerk':'test','gewinner':winners,'waehrung':currency,
                    'betrag_hundertstel':amount,'betrag_art':'je_gewinn','status':''}
        self.records=[
            {'spiel':'lotto','datum':'1987-01-01','zahlen':[1,2,3,4,5,6],'zusatzzahl':7,
             'quoten':[q('6er',15000000,currency='ATS')],'zeile':1},
            {'spiel':'lotto','datum':'2026-09-13','zahlen':[1,2,3,4,5,6],'zusatzzahl':7,
             'quoten':[q('6er',0),q('5er',None,None)],'zeile':2},
            {'spiel':'lotto','datum':'2026-09-13','kennung':'bonus','zahlen':[1,2,3,4,5,6],'zusatzzahl':8,
             'quoten':[q('6er',100)],'zeile':3},
            {'spiel':'joker','datum':'1988-10-02','nummer':'001234','zeile':4},
            {'spiel':'joker','datum':'2026-09-13','nummer':'001234',
             'quoten':[q(str(rank),None if rank>1 else 10000) for rank in range(1,7)],'zeile':5},
        ]
        ingest(self.con,json.dumps(self.records).encode(),'https://example.org/archive',self.records)

    def test_separate_games_and_preserve_unknown_zero_currency_and_identity(self):
        before=self.con.total_changes
        rows=search_quotes(self.con,'lotto',parse_date_filter('13.09.2026'))
        self.assertEqual(len(rows),3)
        self.assertEqual({r['kennung'] for r in rows},{'haupt','bonus'})
        main=[r for r in rows if r['kennung']=='haupt']
        self.assertEqual((main[0]['betrag_hundertstel'],main[0]['gewinner']),(0,0))
        self.assertIsNone(main[1]['betrag_hundertstel']);self.assertIsNone(main[1]['gewinner'])
        old=search_quotes(self.con,'lotto',parse_date_filter('1987'))
        self.assertEqual((old[0]['betrag_hundertstel'],old[0]['waehrung']),(15000000,'ATS'))
        joker=search_quotes(self.con,'joker',parse_date_filter('09.2026'))
        self.assertEqual([r['code'] for r in joker],list('123456'))
        self.assertTrue(all(r['betrag_hundertstel'] is None for r in joker[1:]))
        self.assertEqual(self.con.total_changes,before)

    def test_draw_without_quotes_hidden_and_filters_start_first_digit(self):
        rows=search_quotes(self.con,'joker',parse_date_filter('1988'))
        self.assertEqual(rows,[])
        self.assertEqual(self.con.execute('SELECT count(*) FROM joker_ziehungen').fetchone()[0],2)
        self.assertEqual(len(search_quotes(self.con,'lotto',parse_date_filter('1'))),4)
        self.assertEqual(len(search_quotes(self.con,'joker',parse_date_filter(''))),6)
        self.assertEqual(search_quotes(self.con,'joker',parse_date_filter('2025')),[])
        with self.assertRaisesRegex(ValueError,'L002'):search_quotes(self.con,'invalid',parse_date_filter(''))

    def test_explanations_and_sources_preserve_raw_data(self):
        raw=['So.','28.12.','Ziehung wurde auf den 1.1.1987 verschoben']
        cases=[('L003: invalid literal',raw,'postponed'),
               ('L003: invalid literal',['Mi.','23.12.','e n t f a l l e n'],'cancelled'),
               ('L003: Nicht zugeordnete Archivzeile',['(Einführung von 2 Lottoziehungen pro Woche ab 3.9.1997)'],'archive_note'),
               ('L003: Abweichende Quote',{'betrag_hundertstel':1},'quote_conflict'),
               ('L003: Abweichende Ziehung; manuelle Prüfung erforderlich',{'datum':'2024-06-16'},'draw_conflict'),
               ('L003: Mehrdeutiges doppeltes Joker-Datum im Zusatzarchiv',[],'duplicate'),
               ('L003: Originalreihenfolge oder ZZ weicht ab',[],'invalid_order'),
               ('L003: Abweichende Reihenfolge',[],'order_conflict'),
               ('L003: Quote nicht lesbar: invalid',[],'invalid_quote'),
               ('L003: Unbekannter Inhalt',['keine klare Erklärung'],'unknown')]
        for message,original,expected in cases:
            self.assertEqual(category(message,json.dumps(original,ensure_ascii=False)),expected)
        self.assertEqual(category('L003: invalid','invalid json'),'unknown')
        source=self.con.execute('SELECT id FROM import_quellen').fetchone()[0]
        for line,(message,original,_) in enumerate(cases,1):
            self.con.execute('INSERT INTO import_fehler(quelle_id,zeile,meldung,roh) VALUES(?,?,?,?)',
                             (source,line,message,json.dumps(original,ensure_ascii=False)))
        before=self.con.total_changes;rows=read_reviews(self.con)
        self.assertEqual([r['category'] for r in rows],[c[2] for c in cases])
        self.assertEqual(rows[0]['dates'],['1987-01-01'])
        self.assertEqual(rows[4]['dates'],['2024-06-16'])
        self.assertEqual(rows[0]['uri'],'https://example.org/archive')
        self.assertEqual(json.loads(rows[0]['roh']),raw)
        self.assertEqual(self.con.total_changes,before)


if __name__=='__main__':unittest.main()
