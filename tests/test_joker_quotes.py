"""Belegte Einzelquoten vollständig prüfen und bestehende Angaben erhalten."""
import copy
import json
import sqlite3
import unittest
from lotto45.database import SCHEMA,ingest
from lotto45.joker_quotes import parse_archive,URL


def archive():
    return {'game':'JOKER','maxDrawResultSize':1,'drawResults':[{
        'drawDate':'2024-01-03','payoutReleased':True,
        'results':[{'resultType':'JOKER_NUMBER','resultValues':[{'number':n} for n in [0,0,1,2,3,4]]}],
        'ranks':[{'rankNumber':rank,'numberOfWinners':rank,'amountPerWinner':10000//10**min(rank-1,4),
                  'winAmountLabel':'€ '+{1:'100,00',2:'10,00',3:'1,00',4:'0,10',5:'0,01',6:'0,01'}[rank],
                  'description':'Joker' if rank==1 else 'Endstellen'} for rank in range(1,7)]}]}


class JokerQuotesTests(unittest.TestCase):
    def test_six_ranks_leading_zeros_and_jackpot_pool(self):
        data=archive();top=data['drawResults'][0]['ranks'][0]
        top.update(numberOfWinners=0,amountPerWinner=0,winAmountLabel='€ 439.183,77',description='Doppel Jackpot, zusätzlich zum 1. Rang der nächsten Runde')
        rows,issues=parse_archive(json.dumps(data).encode())
        self.assertEqual(issues,[]);self.assertEqual(rows[0]['nummer'],'001234')
        self.assertEqual(len(rows[0]['quoten']),6)
        q=rows[0]['quoten'][0]
        self.assertEqual((q['betrag_hundertstel'],q['gewinner'],q['status'],q['betrag_art']),(43918377,0,'DJP','jackpot'))

    def test_incomplete_unreleased_duplicate_wrong_amount_rejected(self):
        for change in (lambda d:d.update(maxDrawResultSize=2),
                       lambda d:d['drawResults'][0]['ranks'].pop(),
                       lambda d:d['drawResults'][0].update(payoutReleased=False),
                       lambda d:d['drawResults'][0]['ranks'][0].update(amountPerWinner=1),
                       lambda d:d.update(drawResults=d['drawResults']*2,maxDrawResultSize=2)):
            data=archive();change(data)
            with self.assertRaises(ValueError):parse_archive(json.dumps(data).encode())

    def test_only_missing_values_filled_reimport_idempotent_and_conflicts_kept(self):
        con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row;con.executescript(SCHEMA);self.addCleanup(con.close)
        raw=json.dumps(archive()).encode();records,_=parse_archive(raw)
        before=copy.deepcopy(records)
        before[0]['quoten'][0]['betrag_hundertstel']=99999
        for q in before[0]['quoten'][1:]:q['betrag_hundertstel']=None
        before[0]['quoten'][2]['gewinner']=777
        ingest(con,b'old','old',before)
        result=ingest(con,raw,URL,records,fill_missing_only=True)
        self.assertEqual(result['konflikte'],1)
        rows=con.execute('SELECT * FROM joker_quoten ORDER BY klasse_id').fetchall()
        self.assertEqual(rows[0]['betrag_hundertstel'],99999)
        self.assertEqual(rows[1]['betrag_hundertstel'],1000)
        self.assertEqual(rows[2]['gewinner'],777);self.assertIsNone(rows[2]['betrag_hundertstel'])
        self.assertTrue(ingest(con,raw,URL,records,fill_missing_only=True)['bereits_importiert'])
        self.assertEqual(con.execute('SELECT count(*) FROM joker_ziehungen').fetchone()[0],1)
        self.assertEqual(con.execute('SELECT count(*) FROM aenderungen').fetchone()[0],2)

    def test_later_annual_file_without_amounts_preserves_supplements(self):
        con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row;con.executescript(SCHEMA);self.addCleanup(con.close)
        records,_=parse_archive(json.dumps(archive()).encode())
        ingest(con,b'full',URL,records)
        for q in records[0]['quoten'][1:]:q['betrag_hundertstel']=None
        result=ingest(con,b'annual update','annual.csv',records)
        self.assertEqual(result['konflikte'],0);self.assertEqual(result['aenderungen'],0)
        self.assertEqual(con.execute('SELECT count(*) FROM joker_quoten WHERE betrag_hundertstel IS NULL').fetchone()[0],0)


if __name__=='__main__':unittest.main()
