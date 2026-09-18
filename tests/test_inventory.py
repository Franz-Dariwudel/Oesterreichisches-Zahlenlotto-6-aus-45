"""Bestandszahlen auf kleinen Archiven prüfen, einschließlich leerer Bestände."""
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
import unittest
from lotto45.database import connect,ingest
from lotto45.inventory import read_inventory


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'archive.sqlite3'
        self.con=connect(self.path)

    def tearDown(self):
        self.con.close();self.tmp.cleanup()

    def test_empty_database(self):
        result=read_inventory(self.path)
        self.assertEqual(result['total_rows'],2)  # Archiv- und Erweiterungsversion zählen mit.
        self.assertEqual(result['total_draws'],0)
        self.assertEqual(len(result['tables']),20)
        self.assertEqual(result['games']['lotto']['possible'],8145060)
        self.assertEqual(result['games']['joker']['possible'],1000000)
        for game in result['games'].values():
            self.assertEqual(game['tips'],0)
            self.assertEqual(game['missing_amounts'],0)
            self.assertIsNone(game['first']);self.assertIsNone(game['last'])

    def test_repeated_combinations_sources_and_missing_amounts(self):
        def quote(code,amount):
            return {'klasse':code,'regelwerk':'test','gewinner':0,'betrag_hundertstel':amount,
                    'waehrung':'EUR','betrag_art':'je_gewinn','status':''}
        records=[
            {'spiel':'lotto','datum':'2025-12-31','zahlen':[1,2,3,4,5,6],'zusatzzahl':7,
             'reihenfolge':[6,5,4,3,2,1],'quoten':[quote('6er',0)]},
            {'spiel':'lotto','datum':'2026-01-02','zahlen':[1,2,3,4,5,6],'zusatzzahl':8,
             'quoten':[quote('6er',None)]},
            {'spiel':'joker','datum':'2026-01-02','nummer':'000012','quoten':[quote('1',None)]},
        ]
        raw=json.dumps(records).encode()
        ingest(self.con,raw,'test',records);ingest(self.con,raw,'test',records)
        result=read_inventory(self.path)
        self.assertEqual(result['total_rows'],27)
        self.assertEqual(result['total_draws'],3)
        self.assertEqual(result['tables']['import_quellen'],1)
        self.assertEqual(result['tables']['lotto_ziehungszahlen'],6)
        self.assertEqual(result['games']['lotto'],{'tips':1,'possible':8145060,'draws':2,
            'quotes':2,'first':'2025-12-31','last':'2026-01-02','missing_amounts':1})
        self.assertEqual(result['games']['joker']['tips'],1)
        self.assertEqual(result['games']['joker']['missing_amounts'],1)
        self.con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        before=hashlib.sha256(self.path.read_bytes()).digest()
        result=read_inventory(self.path)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(),before)
        self.assertEqual(result['sizes']['database'],self.path.stat().st_size)

    def test_missing_and_invalid_files_are_not_empty_archives(self):
        absent=self.path.parent/'missing.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):read_inventory(absent)
        self.assertFalse(absent.exists())
        broken=self.path.parent/'broken.sqlite3';broken.write_text('keine Datenbank')
        with self.assertRaises(sqlite3.DatabaseError):read_inventory(broken)


if __name__=='__main__':unittest.main()
