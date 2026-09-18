"""Additive Konzept-Erweiterung; vor jeder Migration eine SQLite-Sicherung.

Das bewährte Archivschema bleibt Version 1. extension_version versioniert die
zusätzlichen Dienste separat, damit alte Lesewerkzeuge weiter funktionieren.
GPL-3.0-only · Josef Lehner.
"""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

EXTENSION = '''
CREATE TABLE IF NOT EXISTS stat_profile(
 id INTEGER PRIMARY KEY, game TEXT NOT NULL CHECK(game IN ('lotto','joker')),
 name TEXT NOT NULL, settings TEXT NOT NULL, updated TEXT NOT NULL, UNIQUE(game,name));
CREATE TABLE IF NOT EXISTS tip_batch(
 id INTEGER PRIMARY KEY, game TEXT NOT NULL CHECK(game IN ('lotto','joker')),
 created TEXT NOT NULL, count INTEGER NOT NULL CHECK(count>0), profile TEXT NOT NULL,
 rng_mode TEXT NOT NULL, seed INTEGER);
CREATE TABLE IF NOT EXISTS batch_tip(
 batch_id INTEGER NOT NULL REFERENCES tip_batch(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, value TEXT NOT NULL,
 PRIMARY KEY(batch_id,position), UNIQUE(batch_id,value));
CREATE TABLE IF NOT EXISTS data_source(
 url TEXT PRIMARY KEY, name TEXT NOT NULL, game TEXT NOT NULL, format TEXT NOT NULL,
 priority INTEGER NOT NULL, enabled INTEGER NOT NULL, last_success TEXT,
 etag TEXT, modified TEXT, checked TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS source_cache(url TEXT PRIMARY KEY, etag TEXT, modified TEXT, sha256 TEXT);
CREATE TABLE IF NOT EXISTS import_run(
 id INTEGER PRIMARY KEY, started TEXT NOT NULL, url TEXT NOT NULL, sha256 TEXT,
 status TEXT NOT NULL, read_count INTEGER NOT NULL DEFAULT 0,
 changed INTEGER NOT NULL DEFAULT 0, rejected INTEGER NOT NULL DEFAULT 0,
 details TEXT NOT NULL);
'''


def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ensure(con, path):
    """Erweiterung genau einmal, transaktionell und mit vorheriger Online-Sicherung."""
    version=con.execute("SELECT value FROM metadata WHERE key='extension_version'").fetchone()
    if version:
        if version[0]!='1':raise ValueError('L011: Unbekannte Erweiterungsversion; passende Programmversion verwenden.')
        return
    # Nur bestehende Archive mit Inhalt sichern; ein frischer Leerbestand braucht kein Backup.
    if con.execute('SELECT 1 FROM lotto_ziehungen LIMIT 1').fetchone() or con.execute('SELECT 1 FROM joker_ziehungen LIMIT 1').fetchone():
        folder=Path(path).parent/'backups';folder.mkdir(exist_ok=True)
        target=folder/(Path(path).stem+'-before-extension-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
        with closing(sqlite3.connect(target)) as copy:con.backup(copy)
    try:
        con.execute('BEGIN IMMEDIATE')
        for statement in EXTENSION.split(';'):
            if statement.strip():con.execute(statement)
        con.execute("INSERT INTO metadata VALUES('extension_version','1')")
        con.commit()
    except Exception:
        con.rollback();raise
