"""DEB-Deinstallation nach Laufzeitänderungen und Schutz fremder Dateien prüfen."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'packaging/installation.py'
spec = importlib.util.spec_from_file_location('deb_installation', SOURCE)
installation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installation)


class DebUninstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.root = self.home / '.local/share/oesterreichisches-zahlenlotto'
        self.exe = Path('/usr/bin/6aus45')

    def tearDown(self):
        self.temp.cleanup()

    def file(self, relative, text='created'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def remove(self):
        installation.remove_state(self.root, self.home, self.exe)

    def test_runtime_database_backups_reports_and_wal_are_removed(self):
        installation.prepare_state(self.root)
        for path in ('data/lotto.sqlite3', 'data/lotto.sqlite3-wal', 'data/lotto.sqlite3-shm',
                     'data/backups/lotto-before-extension.sqlite3', 'data/rejected/archive.csv',
                     'data/lotto_00.sqlite3', 'logs/6aus45_diagnose.json', 'logs/error.log',
                     'config/settings.json', 'help/extra.html', 'languages/extra.json'):
            self.file(path)
        self.file('data/lotto.sqlite3', 'subsequently modified')
        self.remove()
        self.assertFalse(self.root.exists())
        self.remove()  # Wiederholtes Entfernen bleibt möglich.

    def test_old_journal_without_seed_marker_is_cleaned_up(self):
        self.file('installation.json', json.dumps({'files': []}))
        self.file('data/lotto.sqlite3')
        self.file('logs/diagnose.json')
        self.remove()
        self.assertFalse(self.root.exists())

    def test_files_existing_before_installation_remain(self):
        keep = self.file('data/own.sqlite3', 'user database')
        config = self.file('config/settings.json', '{}')
        installation.prepare_state(self.root)
        self.file('data/backups/generated.sqlite3')
        self.file('logs/diagnose.json')
        installation.prepare_state(self.root)  # Update darf Besitznachweis nicht zurücksetzen.
        self.remove()
        self.assertEqual(keep.read_text(), 'user database')
        self.assertEqual(config.read_text(), '{}')
        self.assertFalse((self.root / 'data/backups').exists())

    def test_external_database_and_symlink_target_remain(self):
        installation.prepare_state(self.root)
        outside = self.home / 'own.sqlite3'
        outside.write_text('foreign')
        self.file('config/settings.json', json.dumps({'database': str(outside)}))
        (self.root / 'data').mkdir()
        (self.root / 'data/linked.sqlite3').symlink_to(outside)
        (self.root / 'vendor').symlink_to(self.home / 'foreign-dir', target_is_directory=True)
        (self.home / 'foreign-dir').mkdir()
        other = self.home / 'foreign-dir/keep.txt'
        other.write_text('keep')
        self.remove()
        self.assertEqual(outside.read_text(), 'foreign')
        self.assertEqual(other.read_text(), 'keep')
        self.assertFalse(self.root.exists())

    def test_own_desktop_only_and_untrusted_journal_paths(self):
        data = installation.prepare_state(self.root)
        desktop = self.home / 'TranslatedDesktop/oesterreichisches-zahlenlotto.desktop'
        desktop.parent.mkdir()
        desktop.write_text('[Desktop Entry]\nExec=/usr/bin/6aus45\n')
        foreign = self.home / 'foreign.txt'
        foreign.write_text('foreign')
        wrong_starter = self.home / 'oesterreichisches-zahlenlotto.desktop'
        wrong_starter.write_text('[Desktop Entry]\nExec=/usr/bin/other\n')
        data['files'] = [str(desktop), str(foreign), str(wrong_starter)]
        installation.save_journal(self.root, data)
        self.remove()
        self.assertFalse(desktop.exists())
        self.assertTrue(foreign.exists())
        self.assertTrue(wrong_starter.exists())

    def test_missing_journal_does_not_delete_unknown_folder(self):
        keep = self.file('data/own.sqlite3')
        with self.assertRaisesRegex(RuntimeError, 'Installationsnachweis fehlt'):
            self.remove()
        self.assertTrue(keep.exists())

    def test_root_symlink_is_rejected(self):
        other = self.home / 'outside'
        other.mkdir()
        self.root.parent.mkdir(parents=True)
        self.root.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symbolischer Link'):
            installation.prepare_state(self.root)
        self.assertEqual(list(other.iterdir()), [])

    def test_failure_is_reported_with_path_and_journal_retained(self):
        installation.prepare_state(self.root)
        file = self.file('data/lotto.sqlite3')
        unlink = Path.unlink
        def fail(path, *args, **kwargs):
            if path == file:
                raise PermissionError('denied')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail):
            with self.assertRaisesRegex(RuntimeError, 'data/lotto.sqlite3: denied'):
                self.remove()
        self.assertTrue((self.root / 'installation.json').exists())
        self.remove()
        self.assertFalse(self.root.exists())

    def test_running_application_prevents_incomplete_cleanup(self):
        installation.prepare_state(self.root)
        self.file('lotto45/__init__.py', '')
        self.file('lotto45/__main__.py', "from pathlib import Path\nimport time\nPath('logs/ready').touch()\ntime.sleep(30)\n")
        (self.root / 'logs').mkdir()
        process = subprocess.Popen([sys.executable, '-B', '-m', 'lotto45'], cwd=self.root)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'logs/ready').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.root / 'logs/ready').exists())
            self.assertIn(process.pid, installation.active_processes(self.root))
            with self.assertRaisesRegex(RuntimeError, 'Programm vor der Deinstallation schließen'):
                self.remove()
            self.assertTrue((self.root / 'installation.json').exists())
        finally:
            process.terminate()
            process.wait(timeout=5)
        self.remove()
        self.assertFalse(self.root.exists())


if __name__ == '__main__':
    unittest.main()
