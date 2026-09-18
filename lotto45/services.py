"""Menü-/CLI-Dienste für Integrität, Sicherung, Diagnose."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import json
import sqlite3
from .database import connect,summary
from .exports import atomic_target
from .schema import now
from . import VERSION


def status(path):
    with closing(connect(path,create=False)) as con:
        meta=dict(con.execute('SELECT key,value FROM metadata'))
        counts={g:con.execute(f'SELECT count(*) FROM {g}_ziehungen').fetchone()[0] for g in ('lotto','joker')}
    return {'version':VERSION,'metadata':meta,'counts':counts}


def check(path):
    with closing(connect(path,create=False)) as con:
        integrity=[r[0] for r in con.execute('PRAGMA integrity_check')]
        foreign=[tuple(r) for r in con.execute('PRAGMA foreign_key_check')]
    if integrity!=['ok'] or foreign:raise ValueError('L011: Integritätsprüfung fehlgeschlagen; Original erhalten und Sicherung wiederherstellen.')
    with closing(connect(path)) as con,con:
        con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('last_check',now()))
    return {'integrity':integrity,'foreign_keys':foreign}


def backup(path,target):
    if Path(path).resolve()==Path(target).resolve():raise ValueError('L011: Sicherung benötigt einen anderen Dateinamen.')
    if Path(target).exists():raise ValueError('L011: Sicherungsziel existiert bereits; neuen Namen wählen.')
    with atomic_target(target) as stage:
        with closing(connect(path,create=False)) as con,closing(sqlite3.connect(stage)) as copy:
            con.backup(copy)
            if [r[0] for r in copy.execute('PRAGMA integrity_check')]!=['ok']:raise ValueError('L011: Sicherung ist nicht intakt.')
    with closing(connect(path)) as con,con:con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('last_backup',now()))
    return str(target)


def diagnose(path):
    with closing(connect(path,create=False)) as con:
        data=status(path);data['integrity']=[r[0] for r in con.execute('PRAGMA integrity_check')]
        data['foreign_key_errors']=len(list(con.execute('PRAGMA foreign_key_check')))
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        # Keine Rohdateien, Zugangsdaten, Rechnernamen oder lokalen Pfade exportieren.
        data['metadata']={k:v for k,v in data['metadata'].items() if k in ('schema_version','extension_version','last_check','last_backup','last_update','last_data_check','internet')}
        data['imports']=[dict(r) for r in con.execute('SELECT started,status,read_count,changed,rejected FROM import_run ORDER BY id DESC LIMIT 30')] if 'import_run' in tables else []
        data['sources']=[dict(r) for r in con.execute('SELECT name,game,format,enabled,last_success,checked,status FROM data_source')] if 'data_source' in tables else []
        return data




def import_log(path):
    with closing(connect(path,create=False)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='import_run'").fetchone():return []
        return [dict(r) for r in con.execute('SELECT * FROM import_run ORDER BY id DESC LIMIT 1000')]


def startup(path):
    """DB prüfen, additive Migration ausführen; beschädigte Originale nie ersetzen."""
    from .tempwork import cleanup
    cleanup()
    fresh=not Path(path).exists()
    if not fresh:
        with closing(connect(path,create=False)) as con:
            if [r[0] for r in con.execute('PRAGMA integrity_check')]!=['ok'] or con.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('L011: Datenbank beschädigt. Original bleibt erhalten; Sicherung über Gemeinsam wiederherstellen.')
    with closing(connect(path)) as con:pass
    return fresh

def update_check_report(path, sources, report_dir, progress=lambda event, value: None, cancel=None):
    """Daten aktualisieren, Integrität prüfen und einen lokalen Bericht ablegen.

    Einzelne Fehler verhindern die folgenden Diagnoseschritte nicht. Abbruch
    beendet dagegen den Ablauf. Berichte enthalten keine freien Fehlermeldungen,
    Quellen-URLs oder lokalen Datenbankpfade.
    """
    from .archive_download import download_selected,probe_sources
    result={'files':[], 'errors':[]}
    stages={}
    def stopped():
        if cancel is not None and cancel.is_set():
            raise InterruptedError('L013: Datencheck abgebrochen.')
    def run_stage(name, callback):
        stopped();progress('phase',name)
        try:
            value=callback();stages[name]='ok';return value
        except InterruptedError:raise
        except Exception as error:
            stages[name]=type(error).__name__
            result['errors'].append({'message':str(error)})
            return None
    probes=run_stage('probe_sources',lambda:probe_sources(sources,cancel=cancel))
    result['source_checks']=probes or []
    if probes is not None:
        for source in probes:
            if source['status']!='OK':
                stages['probe_sources']='errors'
                result['errors'].append({'message':source['name']+': '+source['status']})
    progress('phase_result',('probe_sources',stages['probe_sources']))
    downloaded=run_stage('check_data',lambda:download_selected(sources,path,progress=progress,cancel=cancel))
    if downloaded is not None:
        result['files']=downloaded['files'];result['errors'].extend(downloaded['errors'])
        if downloaded['errors']:stages['check_data']='errors'
    progress('phase_result',('check_data',stages['check_data']))
    checked=run_stage('db_check',lambda:check(path))
    progress('phase_result',('db_check',stages['db_check']))
    result['database_ok']=checked is not None
    report=run_stage('diagnose',lambda:diagnose(path))
    stopped()
    if report is None:report={'version':VERSION}
    # Freie Fehlermeldungen können URLs enthalten: nur Status und Anzahl exportieren.
    report['source_checks']=[{'name':item['name'],'status':'OK' if item['status']=='OK' else 'L008',
                              'records':item['records']} for item in result['source_checks']]
    report['workflow']=dict(stages)
    report['error_count']=len(result['errors'])
    try:
        folder=Path(report_dir);folder.mkdir(parents=True,exist_ok=True)
        target=folder/('6aus45_diagnose_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
        with atomic_target(target) as stage:
            stage.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        result['report_path']=str(target)
    except OSError as error:
        stages['diagnose']='write_error'
        result['report_path']=None
        result['errors'].append({'message':'L001: Diagnosebericht konnte nicht gespeichert werden: '+str(error)})
    progress('phase_result',('diagnose',stages['diagnose']))
    result['stages']=dict(stages)
    return result
