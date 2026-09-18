"""Fachliche Suche und lückenlose Seitennavigation auf isoliertem Katalog."""
import itertools
import sqlite3
import unittest

from lotto45.database import SCHEMA, tip_id
from lotto45.tip_search import parse_search, search_tips


def search_catalog(con,query,*args,**kwargs):
    """Die ausdrücklich interne Katalogoption bleibt unabhängig von der Oberfläche."""
    return search_tips(con,query,*args,drawn_only=False,**kwargs)


class TipSearchTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.executescript(SCHEMA)
        self.tips = list(itertools.combinations(range(1, 9), 6))
        self.tips.append((7, 11, 17, 27, 37, 45))
        self.tips.append((11, 17, 27, 37, 44, 45))
        self.con.executemany('INSERT INTO lotto_tipps VALUES(?,?,?,?,?,?,?)',
                             [(tip_id(ns), *ns) for ns in self.tips])
        for date in ('2026-01-01', '2026-01-04'):
            self.con.execute('INSERT INTO lotto_ziehungen(datum,tipp_id,zusatzzahl) VALUES(?,?,?)',
                             (date, tip_id((1, 2, 3, 4, 5, 6)), 7))

    def tearDown(self):
        self.con.close()

    def test_explicit_game_prevents_cross_game_search(self):
        self.assertEqual(parse_search('07',game='lotto').numbers,(7,))
        self.assertEqual(parse_search('001234',game='joker').joker,'001234')
        for text,game in [('001234','lotto'),('1234567','joker'),('1 2 3 4 5 6','joker'),('07','unknown')]:
            with self.subTest(text=text,game=game),self.assertRaisesRegex(ValueError,'L002'):
                parse_search(text,game=game)

    def test_partial_joker_anywhere_and_all_pages(self):
        for value in ('001234','123000','230001','999923','232323','456789'):
            self.con.execute('INSERT INTO joker_tipps VALUES(?)',(value,))
        query=parse_search('23',game='joker')
        rows=[]
        for page in range(3):
            data=search_catalog(self.con,query,page=page,page_size=2)
            self.assertEqual(data['total'],5);rows.extend(r['tip'] for r in data['rows'])
        self.assertEqual(rows,['001234','123000','230001','232323','999923'])
        self.assertEqual(search_catalog(self.con,parse_search('0',game='joker'))['total'],3)
        self.assertEqual(parse_search('7',game='joker').expected,1000000-9**6)
        self.assertEqual(parse_search('00',game='joker').expected,45739)
        self.assertEqual(parse_search('123456',game='joker').expected,1)

    def test_single_number_in_every_position_without_substring_matches(self):
        result = search_catalog(self.con, parse_search('7'))
        expected = sorted(ns for ns in self.tips if 7 in ns)
        self.assertEqual([row['tip'] for row in result['rows']], expected)
        self.assertEqual(result['total'], len(expected))
        self.assertEqual(result['expected'], 1086008)
        self.assertTrue(all(not row['dates'] for row in result['rows']))

    def test_multiple_numbers_require_all_and_ignore_input_order(self):
        result = search_catalog(self.con, parse_search('8, 2'))
        self.assertEqual([row['tip'] for row in result['rows']],
                         [ns for ns in self.tips if {8, 2}.issubset(ns)])

    def test_all_pages_have_every_match_once(self):
        query = parse_search('1');first = search_catalog(self.con, query, page_size=3)
        rows = []
        for page in range(first['pages']):
            data = search_catalog(self.con, query, page=page, page_size=3)
            self.assertEqual(data['first'], page*3+1)
            self.assertEqual(data['last'], min((page+1)*3, data['total']))
            rows.extend(row['tip'] for row in data['rows'])
        self.assertEqual(rows, [ns for ns in self.tips if 1 in ns])
        self.assertEqual(len(rows), len(set(rows)))
        final = search_catalog(self.con, query, page=999999, page_size=3)
        self.assertEqual(final['page'], first['pages']-1)
        self.assertEqual(final['last'], first['total'])

    def test_exact_six_retains_all_draw_dates(self):
        result = search_catalog(self.con, parse_search('6 5 4 3 2 1'))
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['expected'], 1)
        self.assertEqual(result['rows'][0]['tip'], (1, 2, 3, 4, 5, 6))
        self.assertEqual(result['rows'][0]['dates'], ['2026-01-01', '2026-01-04'])

    def test_no_match_and_incomplete_catalog(self):
        result = search_catalog(self.con, parse_search('9'))
        self.assertEqual(result['rows'], [])
        self.assertEqual((result['total'], result['first'], result['last']), (0, 0, 0))
        self.assertGreater(result['expected'], result['total'])

    def test_joker_leading_zeros(self):
        self.con.execute("INSERT INTO joker_tipps VALUES('001234')")
        self.con.execute("INSERT INTO joker_ziehungen(datum,nummer) VALUES('2026-01-01','001234')")
        result = search_catalog(self.con, parse_search('001234'))
        self.assertEqual(result['rows'], [{'tip': '001234', 'dates': ['2026-01-01']}])
        self.assertEqual(result['total'], 1)
        self.assertEqual(search_catalog(self.con, parse_search('999999'))['total'], 0)

    def test_invalid_input(self):
        for text in ('', ' ', ',', '1 1', '0', '46', '-1', '1.5', 'abc', '1 2 3 4 5 6 7', '１２３４５６', '1;DROP TABLE lotto_tipps'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'L002'):
                parse_search(text)
        for page in (-1, 0.5, True):
            with self.assertRaisesRegex(ValueError, 'L002'):
                search_catalog(self.con, parse_search('1'), page=page)


if __name__ == '__main__':
    unittest.main()
