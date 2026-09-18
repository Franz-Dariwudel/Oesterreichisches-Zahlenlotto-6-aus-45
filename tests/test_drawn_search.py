"""Die Standardsuche berücksichtigt nur gezogene Lotto-/Joker-Kombinationen."""
import sqlite3
import unittest
from lotto45.database import SCHEMA,tip_id
from lotto45.tip_search import search_tips,parse_search
from lotto45.quotes import group_months


class DrawnSearchTests(unittest.TestCase):
    def setUp(self):
        self.con=sqlite3.connect(':memory:');self.con.executescript(SCHEMA);self.addCleanup(self.con.close)
        self.tips=[(1,2,3,4,5,6),(1,2,3,4,5,7),(1,2,3,4,5,8),(7,11,17,27,37,45)]
        self.con.executemany('INSERT INTO lotto_tipps VALUES(?,?,?,?,?,?,?)',[(tip_id(t),*t) for t in self.tips])
        for index in (0,2):
            for date in ('2026-01-01','2026-09-13'):
                self.con.execute('INSERT INTO lotto_ziehungen(datum,kennung,tipp_id,zusatzzahl) VALUES(?,?,?,45)',(date,str(index),tip_id(self.tips[index])))
        for number in ('001234','123000','999923','456789'):
            self.con.execute('INSERT INTO joker_tipps VALUES(?)',(number,))
        for number,date in (('001234','2026-01-01'),('001234','2026-09-13'),('999923','2026-09-15')):
            self.con.execute('INSERT INTO joker_ziehungen(datum,nummer) VALUES(?,?)',(date,number))

    def test_only_drawn_lotto_and_all_repeated_dates(self):
        before=self.con.total_changes
        result=search_tips(self.con,parse_search('1',game='lotto'))
        self.assertEqual(result['total'],2)
        self.assertEqual([r['tip'] for r in result['rows']],[self.tips[0],self.tips[2]])
        self.assertTrue(all(len(r['dates'])==2 for r in result['rows']))
        for query in ('7','45','1 2 3 4 5 7'):
            self.assertEqual(search_tips(self.con,parse_search(query,game='lotto'))['total'],0)
        self.assertEqual(search_tips(self.con,parse_search('1 8',game='lotto'))['total'],1)
        self.assertEqual(self.con.total_changes,before)

    def test_drawn_joker_substrings_and_leading_zero(self):
        result=search_tips(self.con,parse_search('23',game='joker'))
        self.assertEqual([r['tip'] for r in result['rows']],['001234','999923'])
        self.assertEqual(search_tips(self.con,parse_search('0',game='joker'))['total'],1)
        self.assertEqual(search_tips(self.con,parse_search('123000',game='joker'))['total'],0)
        self.assertEqual(search_tips(self.con,parse_search('001234',game='joker'))['rows'][0]['dates'],['2026-01-01','2026-09-13'])

    def test_pagination_never_includes_undrawn_combinations(self):
        query=parse_search('1',game='lotto')
        first=search_tips(self.con,query,page=0,page_size=1)
        last=search_tips(self.con,query,page=999,page_size=1)
        self.assertEqual((first['pages'],last['page'],last['last']),(2,1,2))
        self.assertEqual([first['rows'][0]['tip'],last['rows'][0]['tip']],[self.tips[0],self.tips[2]])

    def test_month_groups_keep_year_order_every_rank_and_missing_quotes(self):
        rows=[{'datum':'1988-10-02','klasse_id':None},
              {'datum':'2026-09-13','klasse_id':1},{'datum':'2026-09-13','klasse_id':2},
              {'datum':'2026-01-01','klasse_id':1},{'datum':'2025-09-01','klasse_id':1}]
        groups=group_months(rows)
        self.assertEqual(list(groups),['2026-09','2026-01','2025-09','1988-10'])
        self.assertEqual(sum(len(values) for values in groups.values()),len(rows))
        self.assertIsNone(groups['1988-10'][0]['klasse_id'])
        self.assertEqual(groups['2026-09'],rows[1:3])


if __name__=='__main__':unittest.main()
