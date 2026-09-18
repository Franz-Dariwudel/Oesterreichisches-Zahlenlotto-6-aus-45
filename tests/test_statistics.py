"""Fachliche Statistikprüfung mit manuell nachvollziehbaren Ziehungsfolgen."""
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from lotto45.statistics import Analysis,Draw,KINDS,CHARTS,load_draws
from lotto45.database import connect,ingest


class StatisticsTest(unittest.TestCase):
    def setUp(self):
        self.draws=[Draw(1,'2026-01-01','haupt',(3,12,17,18,31,42),7),
                    Draw(2,'2026-01-04','haupt',(1,2,3,4,5,6),17),
                    Draw(3,'2026-01-07','haupt',(3,12,17,18,31,42),17)]
        self.a=Analysis(self.draws)

    def test_document_example_draw_metrics(self):
        d=self.a.details[0]
        self.assertEqual((d['sum'],d['mean'],d['min'],d['max'],d['span']),(123,20.5,3,42,39))
        self.assertEqual((d['even'],d['odd'],d['low'],d['high']),(3,3,4,2))
        self.assertEqual(d['neighbors'],((17,18),))
        self.assertEqual(d['gaps'],(9,5,1,13,11))
        self.assertEqual((d['gap_min'],d['gap_max'],d['gap_mean']),(1,13,7.8))
        self.assertIsNone(d['repeat'])

    def test_number_gaps_pauses_and_bonus_are_separate(self):
        n=self.a.numbers[16]
        self.assertEqual((n['count'],n['bonus'],n['last'],n['pause']),(2,2,'2026-01-07',0))
        self.assertAlmostEqual(n['percent'],200/3)
        self.assertEqual((n['gap_mean'],n['gap_min'],n['gap_max'],n['historic_pause']),(2,2,2,1))
        n=self.a.numbers[0]
        self.assertEqual((n['count'],n['pause']),(1,1));self.assertIsNone(n['gap_mean'])
        n=self.a.numbers[6]
        self.assertEqual((n['count'],n['bonus'],n['pause'],n['unseen']),(0,1,3,True))
        self.assertIsNone(n['last'])
        self.assertEqual(self.a.numbers[2]['historic_pause'],0)

    def test_binomial_expectation_and_zero_denominators(self):
        n=self.a.numbers[16];mu=3*6/45;sd=math.sqrt(3*(6/45)*(39/45))
        self.assertAlmostEqual(n['expected'],mu);self.assertAlmostEqual(n['sigma'],sd)
        self.assertAlmostEqual(n['delta'],2-mu);self.assertAlmostEqual(n['absolute_delta'],abs(2-mu))
        self.assertAlmostEqual(n['relative_delta'],(2-mu)/mu*100)
        self.assertAlmostEqual(n['z'],(2-mu)/sd)
        empty=Analysis([]).numbers[0]
        for key in ('z','relative_delta','percent','gap_mean'):self.assertIsNone(empty[key])

    def test_all_pairs_and_triples_including_zero_counts(self):
        pairs=self.a.combination_rows(2);triples=self.a.combination_rows(3)
        self.assertEqual(len(pairs),990);self.assertEqual(len(triples),14190)
        self.assertEqual(sum(row[1] for row in pairs),3*15)
        self.assertEqual(sum(row[1] for row in triples),3*20)
        self.assertEqual(next(r for r in pairs if r[0]==(17,18)),((17,18),2,200/3,'2026-01-07',0))
        never=next(r for r in triples if r[0]==(40,41,45))
        self.assertEqual(never[1:],[0,0.0,None,None] if isinstance(never,list) else (0,0.0,None,None))
        self.assertEqual(next(r for r in pairs if r[0]==(1,2))[4],1)

    def test_distributions_ranges_and_endings(self):
        self.assertEqual([r[1] for r in self.a.distribution('even')],[0,0,0,3,0,0,0])
        self.assertEqual([r[1] for r in self.a.distribution('low')],[0,0,0,0,2,0,1])
        ranges=self.a.report('ranges')['tables'][0].rows
        self.assertEqual(ranges[0][1:],(8,800/18,8/3,0,1))
        self.assertEqual(ranges[2][1:],(0,0.0,0,3,0))
        self.assertEqual(sum(self.a.ending_hits.values()),18)
        self.assertEqual((self.a.ending_hits[2],self.a.ending_multiple[2]),(5,2))
        self.assertEqual(self.a.ending_combos[(12,42)],2)
        combos=self.a.report('endings')['tables'][1].rows
        self.assertEqual(len(combos),185)
        self.assertTrue(all(len({n%10 for n in r[0]})==1 for r in combos))

    def test_sums_neighbors_and_repeated_numbers(self):
        r=self.a.report('sums');metrics={key:value for key,value,_ in r['metrics']}
        self.assertEqual(metrics,{'s_min':21,'s_max':123,'s_mean':89,'s_median':123})
        self.assertEqual([r[1] for r in r['tables'][0].rows],[1,0,0,2,0,0,0])
        self.assertEqual(self.a.details[1]['neighbor_count'],5)
        self.assertEqual(self.a.details[1]['run_max'],6)
        n=self.a.report('neighbors');self.assertEqual(len(n['tables'][0].rows),44)
        self.assertEqual(len(n['tables'][1].rows),43)
        self.assertEqual(n['tables'][3].rows,[('2026-01-04','haupt',(1,2,3,4,5,6),6)])
        self.assertEqual(self.a.comparisons,2);self.assertEqual(self.a.repeat_counts,{1:2})
        self.assertEqual(self.a.repeat_numbers,{3:2})
        self.assertEqual(sum(self.a.gaps.values()),15)

    def test_window_retains_previous_draw_context(self):
        a=Analysis(self.draws,1)
        self.assertEqual(a.n,1);self.assertEqual(a.comparisons,1)
        self.assertEqual(a.details[0]['repeat'],(3,))
        self.assertEqual(a.numbers[0]['pause'],1);self.assertTrue(a.numbers[0]['unseen'])
        self.assertIsNone(a.numbers[16]['gap_mean'])
        periods=a.report('periods')['tables'][0].rows
        self.assertEqual(periods[2],(3,3,3,3,3,3,3))

    def test_same_date_draws_are_separate_and_deterministic(self):
        ds=[Draw(2,'2026-01-01','bonus',(1,2,3,4,5,6),7),Draw(1,'2026-01-01','haupt',(1,2,3,4,5,6),8)]
        a=Analysis(ds);self.assertEqual([d.id for d in a.draws],[1,2])
        self.assertEqual(a.numbers[0]['count'],2);self.assertEqual(a.repeat_counts,{4:1})

    def test_ranking_ties_and_all_views_on_empty_archive(self):
        self.assertEqual(Analysis.ranked([(1,3),(2,3),(3,1)]),[(1,1,3),(1,2,3),(3,3,1)])
        empty=Analysis([])
        for kind in KINDS:self.assertEqual(empty.report(kind)['count'],0)
        for kind in CHARTS:self.assertEqual(empty.chart(kind)['count'],0)

    def test_chart_values_and_heatmap(self):
        a=self.a
        self.assertEqual(a.chart('frequency')['values'][2],3)
        self.assertEqual(a.chart('pause')['values'][6],3)
        self.assertTrue(a.chart('pause')['lower_bounds'][6])
        self.assertEqual(a.chart('timeline',17)['values'],[100,50,200/3])
        self.assertEqual(a.chart('deviation',17)['values'],[1-6/45,1-12/45,2-18/45])
        m=a.chart('heatmap')['matrix'];self.assertIsNone(m[16][16])
        self.assertEqual(m[16][17],2);self.assertEqual(m[17][16],2)
        for bad in (-1,True):
            with self.assertRaises(ValueError):Analysis(self.draws,bad)
        with self.assertRaises(ValueError):a.chart('frequency',46)

    def test_loader_reads_without_creating_or_changing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db.sqlite3'
            with self.assertRaises(sqlite3.OperationalError):load_draws(path)
            self.assertFalse(path.exists())
            con=connect(path)
            record={'spiel':'lotto','datum':'2026-01-01','zahlen':[1,2,3,4,5,6],'zusatzzahl':7}
            ingest(con,b'test','test',[record]);con.close()
            before=path.read_bytes();draws=load_draws(path)
            self.assertEqual(len(draws),1);self.assertEqual(draws[0].numbers,(1,2,3,4,5,6))
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
