"""Wiederherstellung: Daten erhalten, defekte Sicherungen ablehnen und sauber abbrechen."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from lotto45 import recovery,settings
from lotto45.database import connect,ingest


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'backup.sqlite3';self.target=self.root/'data/lotto.sqlite3'
        self.records=[{'spiel':'joker','datum':'2026-09-13','nummer':'001234'}]
        self.raw=json.dumps(self.records).encode()
        with closing(connect(self.source)) as con:ingest(con,self.raw,'https://example.org/draws.json',self.records)
        self.before=self.source.read_bytes()

    def assert_clean(self):
        self.assertFalse(list(self.root.rglob('.6aus45-recovery-*')))
        self.assertEqual(self.source.read_bytes(),self.before)

    def test_restore_all_tables_and_original_bytes(self):
        report=recovery.restore(self.source,self.target)
        self.assertEqual(report['path'],self.target)
        self.assertEqual(report['totals']['joker_ziehungen'],1)
        with closing(connect(self.target,create=False)) as con:
            self.assertEqual(con.execute('SELECT original FROM import_quellen').fetchone()[0],self.raw)
            self.assertEqual(con.execute('SELECT count(*) FROM aenderungen').fetchone()[0],1)
            self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0],'delete')
        self.assert_clean()

    def test_occupied_destination_and_sidecars_are_preserved(self):
        self.target.parent.mkdir();self.target.write_bytes(b'existing data')
        report=recovery.restore(self.source,self.target)
        self.assertNotEqual(report['path'],self.target)
        self.assertEqual(self.target.read_bytes(),b'existing data')
        absent=self.target.with_name('other.sqlite3');wal=Path(str(absent)+'-wal');wal.write_bytes(b'pending')
        result=recovery.restore(self.source,absent)
        self.assertNotEqual(result['path'],absent)
        self.assertFalse(absent.exists());self.assertEqual(wal.read_bytes(),b'pending')
        self.assert_clean()

    def test_committed_wal_included_while_writer_open(self):
        with closing(connect(self.source)) as writer:
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute("INSERT INTO joker_tipps VALUES('999999')");writer.commit()
            self.assertGreater(Path(str(self.source)+'-wal').stat().st_size,0)
            report=recovery.restore(self.source,self.target)
            self.assertEqual(report['totals']['joker_tipps'],2)
            self.assertEqual(self.source.read_bytes(),self.before)
        with closing(connect(self.target,create=False)) as con:
            self.assertEqual([r[0] for r in con.execute('SELECT nummer FROM joker_tipps ORDER BY nummer')],['001234','999999'])

    def test_short_names_continue_and_reserve_sidecars(self):
        self.target.parent.mkdir();self.target.write_bytes(b'keep')
        first=recovery.restore(self.source,self.target)['path']
        second=recovery.restore(self.source,self.target)['path']
        self.assertEqual(first.name,'lotto_00.sqlite3')
        self.assertEqual(second.name,'lotto_01.sqlite3')
        reserved=first.with_name('lotto_02.sqlite3-wal');reserved.write_bytes(b'pending')
        third=recovery.restore(self.source,self.target)['path']
        self.assertEqual(third.name,'lotto_03.sqlite3')
        self.assertEqual(reserved.read_bytes(),b'pending')
        self.assertEqual(self.target.read_bytes(),b'keep');self.assert_clean()

    def test_old_long_preference_and_concurrent_collision_use_short_names(self):
        self.target.parent.mkdir()
        long=self.target.with_name('lotto-wiederhergestellt-20260915-123456-abcd.sqlite3')
        link=recovery.os.link;calls=[]
        def race(stage,destination):
            calls.append(destination.name)
            if len(calls)==1:
                destination.write_bytes(b'created elsewhere');raise FileExistsError()
            return link(stage,destination)
        with patch.object(recovery.os,'link',side_effect=race):result=recovery.restore(self.source,long)
        self.assertEqual(result['path'].name,'lotto_01.sqlite3')
        self.assertFalse(long.exists())
        self.assertEqual(long.with_name('lotto_00.sqlite3').read_bytes(),b'created elsewhere')
        self.assert_clean()

    def test_empty_corrupt_foreign_and_missing_databases_rejected(self):
        empty=self.root/'empty.db'
        with closing(connect(empty)):pass
        corrupt=self.root/'corrupt.db';corrupt.write_bytes(b'not sqlite')
        foreign=self.root/'foreign.db'
        with closing(sqlite3.connect(foreign)) as con:con.execute('CREATE TABLE unrelated(x)')
        for source in (empty,corrupt,foreign,self.root/'missing.db'):
            with self.subTest(source=source):
                with self.assertRaisesRegex(recovery.RecoveryError,'L010'):recovery.restore(source,self.target)
                self.assertFalse(self.target.exists());self.assert_clean()

    def test_incompatible_schema_version_and_broken_relationship_rejected(self):
        for sql in ("UPDATE metadata SET value='2' WHERE key='schema_version'",
                    "DELETE FROM joker_tipps",'ALTER TABLE import_quellen RENAME TO other'):
            with self.subTest(sql=sql):
                path=self.root/'wrong.sqlite3';path.write_bytes(self.before)
                with closing(sqlite3.connect(path)) as con:con.execute(sql);con.commit()
                with self.assertRaises(recovery.RecoveryError):recovery.restore(path,self.target)
                self.assertFalse(self.target.exists());self.assert_clean()

    def test_cancel_before_or_during_copy(self):
        for when in ('before','copy'):
            with self.subTest(when=when):
                cancel=threading.Event()
                if when=='before':cancel.set()
                def progress(key,value):
                    if key=='recovery_copy':cancel.set()
                with self.assertRaises(recovery.Cancelled):recovery.restore(self.source,self.target,cancel,progress)
                self.assertFalse(self.target.exists());self.assert_clean()

    def test_failed_publish_retains_existing_data_and_removes_stage(self):
        with patch.object(recovery.os,'link',side_effect=PermissionError('blocked')):
            with self.assertRaisesRegex(recovery.RecoveryError,'L010'):recovery.restore(self.source,self.target)
        self.assertFalse(self.target.exists());self.assert_clean()

    def test_failed_download_never_activates_empty_db(self):
        downloads=self.root/'Downloads';downloads.mkdir();keep=downloads/'keep.txt';keep.write_text('keep')
        sources=[{'name':'Draws','url':'https://example.org/draws.json','enabled':True}]
        def fetch(url):raise OSError('offline')
        with self.assertRaisesRegex(recovery.RecoveryError,'Keine Ziehungen'):
            recovery.rebuild(sources,self.target,download_dir=downloads,fetch=fetch)
        self.assertEqual(list(downloads.iterdir()),[keep]);self.assertEqual(keep.read_text(),'keep')
        self.assertFalse(self.target.exists());self.assert_clean()

    def test_cancel_after_download_and_during_generation(self):
        sources=[{'name':'Draws','url':'https://example.org/draws.json','enabled':True}]
        for when in ('download','generate'):
            with self.subTest(when=when):
                cancel=threading.Event();downloads=self.root/'Downloads';downloads.mkdir(exist_ok=True)
                def fetch(url):
                    if when=='download':cancel.set()
                    return self.raw
                def progress(key,value):
                    if key=='recovery_generate':cancel.set()
                with self.assertRaises(recovery.Cancelled):
                    recovery.rebuild(sources,self.target,cancel,progress,downloads,fetch)
                self.assertFalse(list(downloads.iterdir()))
                self.assertFalse(self.target.exists());self.assert_clean()

    def test_candidates_are_local_possible_backups_not_arbitrary_trash(self):
        data=self.target.parent;backups=data/'backups';backups.mkdir(parents=True)
        trash=self.root/'trash';trash.mkdir()
        expected=[data/'renamed.db',backups/'save.bak',trash/'lotto.sqlite3.2']
        for path in [self.target,*expected,trash/'other.db',data/'readme.txt']:path.touch()
        (data/'link.sqlite3').symlink_to(self.source)
        self.assertEqual(set(recovery.candidates(self.target,data,trash)),set(expected))


class DatabaseSelectionTests(unittest.TestCase):
    def test_default_relative_and_absolute_paths(self):
        root=Path('/example/project')
        self.assertEqual(settings.database_path({},root),root/'data/lotto.sqlite3')
        self.assertEqual(settings.database_path({'database':'data/restored.db'},root),root/'data/restored.db')
        self.assertEqual(settings.database_path({'database':'/other/restored.db'},root),Path('/other/restored.db'))
        for value in ('',False,[],{},'\x00','   '):
            with self.assertRaisesRegex(ValueError,'L004'):settings.database_path({'database':value},root)

    def test_selection_persists_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as name,patch.object(settings,'ROOT',Path(name)):
            config={'database':'data/restored.sqlite3','language':'en','repository':'owner/project'}
            settings.save(config)
            self.assertEqual(settings.load(),{**config,'max_tips':10000})
            self.assertEqual(settings.database_path(settings.load()),Path(name)/'data/restored.sqlite3')
