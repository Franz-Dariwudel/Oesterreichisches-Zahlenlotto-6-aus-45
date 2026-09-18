"""Fehlende Archive bei Anzeigen nicht erzeugen; ausdrückliche Importe erlauben."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from lotto45.database import connect


class MissingDatabaseTests(unittest.TestCase):
    def test_read_missing_does_not_create_directory_or_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'missing'/'lotto.sqlite3'
            with self.assertRaises(sqlite3.OperationalError):connect(path,create=False)
            self.assertFalse(path.parent.exists())

    def test_read_connection_cannot_change_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lotto.sqlite3'
            with closing(connect(path)) as con:
                con.execute("INSERT INTO joker_tipps VALUES('001234')");con.commit()
            before=path.read_bytes()
            with closing(connect(path,create=False)) as con:
                self.assertEqual(con.execute('SELECT nummer FROM joker_tipps').fetchone()[0],'001234')
                with self.assertRaises(sqlite3.OperationalError):con.execute('DELETE FROM joker_tipps')
            self.assertEqual(path.read_bytes(),before)

    def cli(self,root,*args):
        code=('import sys; from pathlib import Path; from lotto45 import __main__ as entry; '
              "entry.ROOT=Path(sys.argv[1]); sys.argv=['lotto45',*sys.argv[2:]]; sys.exit(entry.main())")
        return subprocess.run([sys.executable,'-B','-c',code,str(root),*args],
                              cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=15)

    def test_cli_inspection_preserves_missing_or_renamed_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);renamed=root/'lotto_0.sqlite3'
            with closing(connect(renamed)):pass
            before=renamed.read_bytes()
            for flag in ('--summary','--check'):
                with self.subTest(flag=flag):
                    result=self.cli(root,flag)
                    self.assertEqual(result.returncode,1)
                    self.assertIn('L001',result.stderr)
                    self.assertIn(str(root/'data/lotto.sqlite3'),result.stderr)
                    self.assertIn('L001',(root/'logs/error.log').read_text())
                    self.assertFalse((root/'data').exists())
                    self.assertEqual(renamed.read_bytes(),before)

    def test_explicit_import_can_create_new_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'draws.json'
            source.write_text(json.dumps([{'spiel':'joker','datum':'2026-09-13','nummer':'001234'}]))
            result=self.cli(root,'--import-json',str(source))
            self.assertEqual(result.returncode,0,result.stderr)
            with closing(connect(root/'data/lotto.sqlite3',create=False)) as con:
                self.assertEqual(con.execute('SELECT nummer FROM joker_ziehungen').fetchone()[0],'001234')

    def test_cli_uses_saved_selection_and_explicit_path_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);selected=root/'restored.sqlite3'
            with closing(connect(selected)):pass
            (root/'config').mkdir()
            (root/'config/settings.json').write_text(json.dumps({'database':str(selected)}))
            result=self.cli(root,'--check')
            self.assertEqual(result.returncode,0,result.stderr)
            missing=root/'missing.sqlite3'
            result=self.cli(root,'--db',str(missing),'--check')
            self.assertEqual(result.returncode,1)
            self.assertIn(str(missing),result.stderr)
            self.assertFalse(missing.exists())
