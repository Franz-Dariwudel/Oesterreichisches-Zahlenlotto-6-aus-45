"""Geprüfte Datenbankkopien und Neuaufbau ohne Überschreiben bestehender Dateien.

Sicherungen mit SQLite kopieren, damit bestätigte WAL-Daten erhalten bleiben.
Erst fertige, geprüfte Archive atomar unter einem freien Namen bereitstellen.
Die aktive Auswahl speichert anschließend die Oberfläche in der Konfiguration.
"""
from contextlib import closing,contextmanager
import itertools
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .database import SCHEMA,connect,generate
from . import archive_download


class RecoveryError(ValueError):
    """L010: Wiederherstellung fehlgeschlagen; bestehende Dateien bleiben erhalten."""


class Cancelled(Exception):
    """Vom Benutzer abgebrochener Vorgang."""


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():raise Cancelled()


def candidates(expected,data_dir,trash_dir=None):
    """Mögliche Dateien im Datenordner und passende Lotto-Dateien im Papierkorb."""
    expected=Path(expected).absolute()
    trash=Path(trash_dir) if trash_dir is not None else Path.home()/'.local/share/Trash/files'
    result=[]
    for folder in dict.fromkeys((Path(expected).parent,Path(data_dir),Path(data_dir)/'backups',trash)):
        try:items=sorted(folder.iterdir())
        except OSError:continue
        for path in items:
            name=path.name.lower()
            suitable=path.suffix.lower() in ('.sqlite3','.sqlite','.db','.bak')
            if folder==trash:suitable=name.startswith('lotto') and any(ext in name for ext in ('.sqlite3','.sqlite','.db'))
            if suitable and path.absolute()!=expected and not path.is_symlink() and path.is_file():
                if path not in result:result.append(path)
    return result


@contextmanager
def operation(cancel):
    try:
        check_cancel(cancel)
        yield
    except Cancelled:raise
    except RecoveryError:raise
    except Exception as error:
        check_cancel(cancel)
        raise RecoveryError(f'L010: {error}') from error


def validate(path,cancel=None,require_data=True):
    """Schema, Integrität und Beziehungen prüfen; nur normale Archivetabellen zulassen."""
    with operation(cancel),closing(connect(path,create=False)) as con,closing(sqlite3.connect(':memory:')) as reference:
        con.set_progress_handler(lambda:int(cancel is not None and cancel.is_set()),10000)
        con.execute('PRAGMA trusted_schema=OFF')
        reference.executescript(SCHEMA)
        required=[r[0] for r in reference.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        existing={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in required:
            if table not in existing:raise ValueError('Keine passende 6-aus-45-Datenbank: '+table)
            actual={r[1:3] for r in con.execute(f'PRAGMA table_info({table})')}
            columns={r[1:3] for r in reference.execute(f'PRAGMA table_info({table})')}
            if not columns.issubset(actual):raise ValueError('Unvollständige Archivtabelle: '+table)
        version=con.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        if not version or version[0]!='1':raise ValueError('Unbekannte Datenbankversion')
        if [r[0] for r in con.execute('PRAGMA integrity_check')]!=['ok']:
            raise ValueError('Datenbank ist beschädigt')
        if con.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Datenbankbeziehungen sind beschädigt')
        totals={table:con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in ('lotto_tipps','joker_tipps','lotto_ziehungen','joker_ziehungen')}
        if require_data and not any(totals.values()):raise ValueError('Ausgewählte Datenbank ist leer')
        check_cancel(cancel)
        return totals


def numbered_paths(folder):
    """Kurze Folgennamen ab lotto_00; vorhandene Dateien und SQLite-Reste mitzählen."""
    folder=Path(folder);number=0
    for path in folder.iterdir():
        match=re.fullmatch(r'lotto_([0-9]+)\.sqlite3(?:-wal|-shm)?',path.name)
        if match:number=max(number,int(match[1])+1)
    for number in itertools.count(number):yield folder/f'lotto_{number:02d}.sqlite3'


def publish(stage,preferred,cancel):
    """Atomar unter freiem Namen ablegen; alte lange Namen durch Kurzformen ersetzen."""
    check_cancel(cancel)
    preferred=Path(preferred)
    targets=numbered_paths(preferred.parent)
    if not preferred.name.startswith('lotto-wiederhergestellt-'):
        targets=itertools.chain((preferred,),targets)
    for destination in targets:
        check_cancel(cancel)
        if any(os.path.lexists(str(destination)+ext) for ext in ('','-wal','-shm')):continue
        try:os.link(stage,destination)
        except FileExistsError:continue
        return destination


def restore(source,preferred,cancel=None,progress=lambda key,value:None):
    """Eine Sicherung einschließlich bestätigter WAL-Daten in eine neue Datei kopieren."""
    source=Path(source);preferred=Path(preferred).absolute()
    with operation(cancel):
        progress('recovery_check',source.name)
        # Bereits vor dem Kopieren fachfremde oder beschädigte Dateien zurückweisen.
        validate(source,cancel)
        preferred.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.6aus45-recovery-',dir=preferred.parent) as temp:
            stage=Path(temp)/'archive.sqlite3'
            with closing(connect(source,create=False)) as original,closing(sqlite3.connect(stage)) as target:
                def copied(status,remaining,total):
                    check_cancel(cancel)
                    progress('recovery_copy',f'{100*(total-remaining)//max(total,1)} %')
                original.backup(target,pages=1024,progress=copied)
                target.execute('PRAGMA journal_mode=DELETE')
            progress('recovery_check',source.name)
            totals=validate(stage,cancel)
            destination=publish(stage,preferred,cancel)
        return {'path':destination,'totals':totals,'errors':[]}


def rebuild(sources,preferred,cancel=None,progress=lambda key,value:None,download_dir=None,fetch=None):
    """Verfügbare Ziehungen laden und beide vollständigen Tippkataloge neu erzeugen."""
    preferred=Path(preferred).absolute()
    with operation(cancel):
        preferred.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.6aus45-recovery-',dir=preferred.parent) as temp:
            stage=Path(temp)/'archive.sqlite3'
            def downloading(event,value):
                check_cancel(cancel);progress('recovery_download',value)
            report=archive_download.download_selected(sources,stage,download_dir=download_dir,
                fetch=fetch or archive_download.fetch_url,progress=downloading)
            check_cancel(cancel)
            with closing(connect(stage)) as con:
                draws=sum(con.execute(f'SELECT count(*) FROM {game}_ziehungen').fetchone()[0] for game in ('lotto','joker'))
                if not draws:raise ValueError('Keine Ziehungen heruntergeladen; Quellen und Verbindung prüfen')
                con.set_progress_handler(lambda:int(cancel is not None and cancel.is_set()),10000)
                def generating(value):
                    check_cancel(cancel);progress('recovery_generate',value)
                progress('recovery_generate','')
                # Das Konzept speichert nur historische Ziehungen; kein Universum-Aufbau.
                generating(str(draws))
                con.execute('PRAGMA journal_mode=DELETE')
            progress('recovery_check','')
            totals=validate(stage,cancel)
            destination=publish(stage,preferred,cancel)
        return {'path':destination,'totals':totals,'errors':report['errors']}
