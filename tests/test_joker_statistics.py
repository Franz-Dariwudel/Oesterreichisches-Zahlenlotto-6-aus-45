"""Stellenbezogene Joker-Auswertung und datierte Standardbeträge prüfen."""
from pathlib import Path
import tempfile
import unittest
from lotto45.joker_statistics import JokerAnalysis,load_joker
from lotto45.joker_rules import standard_amount
from lotto45.database import connect,ingest


class JokerTest(unittest.TestCase):
    def setUp(self):
        self.draws=[(1,'2026-01-01','haupt','001234'),(2,'2026-01-04','haupt','991234'),(3,'2026-01-07','haupt','001234')]

    def test_digit_positions_and_leading_zeros(self):
        a=JokerAnalysis(self.draws);r=a.report()
        self.assertEqual(a.hits[0],4);self.assertEqual(a.with_digit[0],2)
        self.assertEqual(a.positions[1,0],2);self.assertEqual(a.positions[2,0],2)
        self.assertEqual(sum(a.hits.values()),18);self.assertEqual(a.counts['001234'],2)
        self.assertEqual(r['metrics'][0][1],'001234')
        self.assertEqual(r['tables'][6].rows[0],('2026-01-07','haupt','001234',10,5))

    def test_all_suffixes_and_latest_occurrence(self):
        a=JokerAnalysis(self.draws);tables=a.report()['tables']
        self.assertEqual([len(t.rows) for t in tables[2:5]],[10,100,1000])
        self.assertEqual(tables[4].rows[0],('234',3,100.0,'2026-01-07',0))
        self.assertEqual(next(row for row in tables[4].rows if row[0]=='000'),('000',0,0.0,None,None))

    def test_window_comparison_and_empty(self):
        a=JokerAnalysis(self.draws,1)
        self.assertEqual(a.n,1);self.assertEqual(a.hits[0],2)
        self.assertEqual(a.report()['tables'][-1].rows[0],(0,4,4,4,4,4,4))
        a=JokerAnalysis([]);r=a.report()
        self.assertIsNone(r['first']);self.assertIsNone(r['tables'][0].rows[0][2])

    def test_read_only_and_no_joker_catalog_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'db';con=connect(p)
            ingest(con,b'joker','test',[{'spiel':'joker','datum':'2026-01-01','nummer':'001234'}]);con.close()
            before=p.read_bytes();self.assertEqual(load_joker(p)[0][3],'001234');self.assertEqual(p.read_bytes(),before)

    def test_prize_plan_has_date_boundaries(self):
        self.assertEqual([standard_amount('2026-09-13',rank) for rank in range(1,7)],[None,1200000,120000,12000,1200,250])
        self.assertIsNone(standard_amount('2025-07-03',2));self.assertEqual(standard_amount('2025-07-04',2),1200000)
        self.assertIsNone(standard_amount('2026-09-16',2))
