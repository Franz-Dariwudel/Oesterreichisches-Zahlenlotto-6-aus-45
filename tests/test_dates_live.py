"""Datumsdarstellung, Kalendervalidierung und Teileingaben auf echten Suchabfragen."""
import sqlite3
import unittest
from lotto45.date_display import format_date,format_log_dates
from lotto45.draw_search import parse_period,parse_date_filter,search_live_draws
from lotto45.database import SCHEMA,tip_id


class DateLiveTests(unittest.TestCase):
    def test_display_preserves_missing_and_draw_identifier(self):
        self.assertEqual(format_date(None),'—')
        self.assertEqual(format_date('2026-09-13'),'So. 13.09.2026')
        self.assertEqual(format_date('2026-09'),'09.2026')
        self.assertEqual(format_date('2026-09-13 · bonus'),'So. 13.09.2026 · bonus')
        self.assertEqual(format_date('1987-01-01 12:34:56'),'Do. 01.01.1987 12:34:56')
        self.assertEqual(format_log_dates('2026-09-15 09:52:48,473 WARNING\npath 2026-09-15.json'),
                         '15.09.2026 09:52:48,473 WARNING\npath 2026-09-15.json')

    def test_full_dates_and_months_keep_iso_bounds(self):
        for text,start,end,label in [('29.02.2024','2024-02-29','2024-02-29','Do. 29.02.2024'),
                                     ('2.2024','2024-02-01','2024-02-29','02.2024'),
                                     ('2026/09','2026-09-01','2026-09-30','09.2026'),
                                     ('1.1.1987','1987-01-01','1987-01-01','Do. 01.01.1987')]:
            with self.subTest(text=text):
                p=parse_period(text);self.assertEqual((p.start,p.end,p.label),(start,end,label))
        for text in ('29.02.2025','2025-02-29','31.04.2026','13.2026','0000','2026/13','00','32','1; DROP TABLE'):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'L002'):parse_date_filter(text)

    def test_partial_date_components(self):
        for text,yes,no in [('1','2026-09-13','2026-09-23'),('1','1987-01-01','1987-01-02'),
                            ('202','2026-09-13','1987-01-01'),('13.','2026-09-13','2026-09-23'),
                            ('13.0','2026-09-13','2026-10-13'),('13.09.20','2026-09-13','1999-09-13'),
                            ('09.202','2026-09-13','2026-10-13'),('2026/0','2026-09-13','2026-10-13')]:
            with self.subTest(text=text):
                query=parse_date_filter(text);self.assertTrue(query.matches(yes));self.assertFalse(query.matches(no))

    def test_live_query_keeps_game_number_filter_and_originals(self):
        con=sqlite3.connect(':memory:');con.executescript(SCHEMA)
        try:
            tid=tip_id((1,2,3,4,5,6));con.execute('INSERT INTO lotto_tipps VALUES(?,?,?,?,?,?,?)',(tid,1,2,3,4,5,6))
            con.execute("INSERT INTO joker_tipps VALUES('123456')")
            for date in ('1987-01-01','2026-09-13','2026-09-23'):
                con.execute('INSERT INTO lotto_ziehungen(datum,tipp_id,zusatzzahl) VALUES(?,?,7)',(date,tid))
                con.execute('INSERT INTO joker_ziehungen(datum,nummer) VALUES(?,?)',(date,'123456'))
            before=con.total_changes
            for game in ('lotto','joker'):
                result=search_live_draws(con,parse_date_filter('1'),game=game)
                self.assertEqual([r['datum'] for r in result],['2026-09-13','1987-01-01'])
                self.assertEqual({r['spiel'] for r in result},{game})
            self.assertEqual(len(search_live_draws(con,parse_date_filter('09.2026'),game='lotto')),2)
            self.assertEqual(len(search_live_draws(con,parse_date_filter(''),(1,),game='lotto')),3)
            self.assertEqual(search_live_draws(con,parse_date_filter(''),(7,),game='lotto'),[])
            self.assertEqual(con.total_changes,before)
        finally:con.close()
