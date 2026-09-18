"""Datumssuche: Kalendergrenzen, beide Spiele und mehrere Ziehungen je Tag."""
import sqlite3
import unittest

from lotto45.database import SCHEMA,tip_id
from lotto45.draw_search import parse_period,parse_draw_numbers,search_draws


class DrawSearchTest(unittest.TestCase):
    def setUp(self):
        self.con=sqlite3.connect(':memory:');self.con.executescript(SCHEMA)
        self.tid=tip_id((1,2,3,4,5,6))
        self.con.execute('INSERT INTO lotto_tipps VALUES(?,?,?,?,?,?,?)',(self.tid,1,2,3,4,5,6))
        self.con.execute("INSERT INTO joker_tipps VALUES('001234')")
        self.dates=('2023-12-31','2024-01-01','2024-02-01','2024-02-29','2024-03-01','2024-12-31','2025-01-01')
        for date in self.dates:
            self.con.execute('INSERT INTO lotto_ziehungen(datum,tipp_id,zusatzzahl,extras) VALUES(?,?,?,?)',(date,self.tid,7,'{"original":"retained"}'))
            self.con.execute('INSERT INTO joker_ziehungen(datum,nummer) VALUES(?,?)',(date,'001234'))
        self.con.execute("INSERT INTO lotto_ziehungen(datum,kennung,tipp_id,zusatzzahl) VALUES('2024-02-29','bonus',?,8)",(self.tid,))

    def tearDown(self):
        self.con.close()

    def test_explicit_game_keeps_date_results_separate(self):
        period=parse_period('2024/02');before=self.con.total_changes
        for game,count in [('lotto',3),('joker',2)]:
            rows=search_draws(self.con,period,game=game)
            self.assertEqual(len(rows),count)
            self.assertEqual({row['spiel'] for row in rows},{game})
        self.assertEqual(self.con.total_changes,before)
        with self.assertRaisesRegex(ValueError,'L002'):search_draws(self.con,period,(1,),game='joker')
        with self.assertRaisesRegex(ValueError,'L002'):search_draws(self.con,period,game='invalid')

    def test_calendar_bounds(self):
        cases={
            '2024':('2024-01-01','2024-12-31'),
            '2024/2':('2024-02-01','2024-02-29'),
            '2024-02':('2024-02-01','2024-02-29'),
            '2025/02':('2025-02-01','2025-02-28'),
            '2024/02/29':('2024-02-29','2024-02-29'),
            '2026-9-3':('2026-09-03','2026-09-03'),
            '0001':('0001-01-01','0001-12-31'),
            '9999/12':('9999-12-01','9999-12-31'),
            '9999':('9999-01-01','9999-12-31'),
        }
        for text,bounds in cases.items():
            with self.subTest(text=text):
                period=parse_period(text);self.assertEqual((period.start,period.end),bounds)

    def test_year_excludes_adjacent_years_includes_endpoints(self):
        rows=search_draws(self.con,parse_period('2024'))
        self.assertEqual(len(rows),11)
        self.assertEqual({row['datum'] for row in rows},set(self.dates[1:-1]))
        self.assertEqual(rows[0]['datum'],'2024-12-31')
        self.assertEqual(rows[0]['spiel'],'lotto')
        self.assertEqual(rows[-1]['datum'],'2024-01-01')

    def test_month_and_exact_day_keep_both_games_and_draw_kinds(self):
        rows=search_draws(self.con,parse_period('2024/02'))
        self.assertEqual(len(rows),5)
        self.assertEqual({row['datum'] for row in rows},{'2024-02-01','2024-02-29'})
        day=search_draws(self.con,parse_period('2024-02-29'))
        self.assertEqual([(row['spiel'],row['kennung']) for row in day],[('lotto','haupt'),('lotto','bonus'),('joker','haupt')])
        self.assertEqual(day[0]['zusatzzahl'],7)
        self.assertEqual(day[0]['extras'],'{"original":"retained"}')
        self.assertEqual(day[-1]['nummer'],'001234')

    def test_empty_period_does_not_modify_data(self):
        before=self.con.total_changes
        self.assertEqual(search_draws(self.con,parse_period('2022')),[])
        self.assertEqual(search_draws(self.con,parse_period('2024/04')),[])
        self.assertEqual(self.con.total_changes,before)

    def test_invalid_periods(self):
        for text in ('',' ','26','20260','0000','2026/0','2026/13','2025-02-29','2024/02/30','2026/04/31',
                     '2026/09-13','2026-09/13','2026/','2026/09/','2026/001','2026-01-00','20260913',
                     '2026;DROP TABLE lotto_ziehungen','２０２６','September 2026'):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'L002'):
                parse_period(text)

    def test_optional_lotto_numbers(self):
        self.assertEqual(parse_draw_numbers('  '),())
        self.assertEqual(parse_draw_numbers('7'),(7,))
        self.assertEqual(parse_draw_numbers('45, 1 07'),(1,7,45))
        self.assertEqual(parse_draw_numbers('6 5 4 3 2 1'),(1,2,3,4,5,6))
        for text in ('0','46','7 7','1.5','-1','1 2 3 4 5 6 7','abc','001234','７',','):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'L002'):
                parse_draw_numbers(text)

    def test_number_filter_selects_only_lotto_main_numbers(self):
        period=parse_period('2024')
        rows=search_draws(self.con,period,(1,))
        self.assertEqual(len(rows),6)
        self.assertTrue(all(row['spiel']=='lotto' for row in rows))
        # 7 kommt nur als Zusatzzahl vor und darf deshalb keinen Treffer liefern.
        self.assertEqual(search_draws(self.con,period,(7,)),[])
        self.assertEqual(len(search_draws(self.con,period,())),11)

    def test_multiple_numbers_and_period_must_all_match(self):
        tip=(1,7,17,23,37,45);tid=tip_id(tip)
        self.con.execute('INSERT INTO lotto_tipps VALUES(?,?,?,?,?,?,?)',(tid,*tip))
        for date in ('2023-02-17','2024-02-17','2024-03-01','2025-02-17'):
            self.con.execute('INSERT INTO lotto_ziehungen(datum,kennung,tipp_id,zusatzzahl) VALUES(?,?,?,?)',(date,'zahlenfilter',tid,8))
        other=(1,7,17,24,37,45);other_id=tip_id(other)
        self.con.execute('INSERT INTO lotto_tipps VALUES(?,?,?,?,?,?,?)',(other_id,*other))
        self.con.execute("INSERT INTO lotto_ziehungen(datum,tipp_id,zusatzzahl) VALUES('2024-02-18',?,23)",(other_id,))
        before=self.con.total_changes
        year=search_draws(self.con,parse_period('2024'),(23,7))
        self.assertEqual([r['datum'] for r in year],['2024-03-01','2024-02-17'])
        month=search_draws(self.con,parse_period('2024/02'),(7,23))
        self.assertEqual([r['datum'] for r in month],['2024-02-17'])
        self.assertEqual(len(search_draws(self.con,parse_period('2024-02-17'),(7,23))),1)
        self.assertEqual(search_draws(self.con,parse_period('2024-02-18'),(7,23)),[])
        self.assertEqual(len(search_draws(self.con,parse_period('2024'),tip)),2)
        self.assertEqual(self.con.total_changes,before)

    def test_invalid_number_parameters_are_rejected(self):
        for numbers in ((0,),(46,),(True,),(1.5,),(7,7),(1,2,3,4,5,6,7),('7',)):
            with self.subTest(numbers=numbers),self.assertRaisesRegex(ValueError,'L002'):
                search_draws(self.con,parse_period('2024'),numbers)


if __name__=='__main__':
    unittest.main()
