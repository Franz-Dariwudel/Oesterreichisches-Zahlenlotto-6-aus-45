"""CLI-Einstieg; ohne Parameter GTK-Ansicht starten. GPL-3.0-only."""
import argparse
import json
import logging
from contextlib import closing
from pathlib import Path
import sys
from . import VERSION
from .database import connect,generate,ingest,summary
from .importers import parse_lotto,parse_joker_pdf,parse_joker_csv
from .statistics import Analysis,load_draws,KINDS,CHARTS,WINDOWS
from dataclasses import asdict

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description='Lotto 6 aus 45 – Tippkatalog und verlustfreies Ziehungsarchiv')
    parser.add_argument('--version',action='version',version=VERSION)
    parser.add_argument('--db',type=Path,help='SQLite-Datenbank; Standard: gespeicherte Auswahl oder data/lotto.sqlite3')
    parser.add_argument('--download',action='store_true',help='Markierte Archiv-Webseiten herunterladen und importieren')
    parser.add_argument('--generate',action='store_true',help='Alle Lotto- und Joker-Tipps erzeugen')
    parser.add_argument('--import-csv',type=Path,help='Offizielles Lotto-CSV importieren')
    parser.add_argument('--import-joker-pdf',type=Path,help='Offizielles Joker-Jahres-PDF importieren (pdftotext erforderlich)')
    parser.add_argument('--source',help='Quellen-URL zum Import')
    parser.add_argument('--import-json',type=Path,help='JSON mit Liste von Ziehungen importieren')
    parser.add_argument('--allow-corrections',action='store_true',help='Abweichende Werte mit Änderungshistorie übernehmen (neuer Quellenstand erforderlich)')
    parser.add_argument('--summary',action='store_true',help='Datenbestand anzeigen')
    parser.add_argument('--check',action='store_true',help='Integrität und Fremdschlüssel prüfen')
    parser.add_argument('--stats',choices=(*KINDS,'joker','patterns'),help='Lotto-Statistik als JSON ausgeben; liest die Datenbank ohne Änderungen')
    parser.add_argument('--last',type=int,choices=(0,*WINDOWS),default=0,help='Statistik: letzte N Ziehungen, 0 = alle (Standard)')
    parser.add_argument('--chart',choices=CHARTS,default='frequency',help='Diagrammdaten für --stats charts (Standard: frequency)')
    parser.add_argument('--stats-number',type=int,choices=range(1,46),default=1,metavar='1..45',help='Zahl für Zeitverlaufsdiagramme')
    parser.add_argument('--tips',type=int,help='Neue Tippserie erzeugen, positive Anzahl')
    parser.add_argument('--game',choices=('lotto','joker'),default='lotto')
    parser.add_argument('--profile',nargs='?',const='',help='Gespeichertes Profil tatsächlich ausführen; ohne Namen eingestelltes Profil')
    parser.add_argument('--seed',type=int,help='Ausschließlich reproduzierbarer TEST-Modus')
    parser.add_argument('--export',type=Path,help='Tippserie als CSV speichern')
    parser.add_argument('--backup',type=Path,help='Datenbank per SQLite sichern (neuer Dateiname)')
    parser.add_argument('--diagnose',action='store_true',help='Diagnose ohne private Rohdaten als JSON')
    parser.add_argument('--from-date',default='',help='Statistikbeginn YYYY-MM-DD')
    parser.add_argument('--to-date',default='',help='Statistikende YYYY-MM-DD')
    parser.add_argument('--weekday',type=int,choices=range(7),help='Statistik: 0 Montag bis 6 Sonntag')
    parser.add_argument('--draw-kind',default='',help='Statistik: Ziehungstyp')
    args = parser.parse_args()
    if args.stats and any((args.download,args.generate,args.import_csv,args.import_json,args.import_joker_pdf,args.summary,args.check)):
        parser.error('--stats separat von Import-, Download- und Prüfaktionen aufrufen')
    modes=sum((args.tips is not None,bool(args.backup),args.diagnose,bool(args.stats),any((args.download,args.generate,args.import_csv,args.import_json,args.import_joker_pdf,args.summary,args.check))))
    if modes>1:parser.error('Tipp-Erstellung, Sicherung, Diagnose, Statistik und Archivaktionen getrennt aufrufen')
    if (args.profile is not None or args.seed is not None or args.export) and args.tips is None:parser.error('--profile/--seed/--export benötigen --tips')
    if args.export and args.export.suffix.lower()!='.csv':parser.error('--export unterstützt ausschließlich CSV')
    from .tempwork import cleanup
    cleanup()
    log_options=dict(level=logging.WARNING,force=True,format='%(asctime)s,%(msecs)03d %(levelname)s %(message)s',
                     datefmt='%d.%m.%Y %H:%M:%S')
    try:
        (ROOT/'logs').mkdir(exist_ok=True)
        # Jeder Programmstart beginnt ein neues Protokoll; Datenbanken bleiben erhalten.
        logging.basicConfig(filename=ROOT/'logs/error.log',filemode='w',encoding='utf-8',**log_options)
    except OSError as error:
        logging.basicConfig(**log_options)
        logging.error('L001: Fehlerprotokoll %s kann nicht neu angelegt werden: %s. '
                      'Pfad und Schreibrechte prüfen; Meldungen erscheinen im Terminal.',ROOT/'logs/error.log',error)
    try:
        if not any((args.download,args.generate,args.import_csv,args.import_json,args.import_joker_pdf,args.summary,args.check,args.stats,args.tips is not None,args.backup,args.diagnose)):
            # Die Oberfläche meldet fehlende Archive sichtbar, ohne eine Ersatzdatei anzulegen.
            from .app import run
            return run(args.db)
        if args.db is None:
            from . import settings
            args.db=settings.database_path(settings.load(ROOT),ROOT)
        if args.tips is not None:
            from . import tips,settings
            with closing(connect(args.db)):pass
            profile=tips.selected_profile(args.db,args.game,args.profile or None) if args.profile is not None else None
            config=settings.load(ROOT)
            batch=tips.create_batch(args.db,args.game,args.tips,profile,config.get('max_tips',10000),args.seed)
            if args.export:
                from .exports import export_batch
                export_batch(batch,args.export,config.get('language','de'))
            print(json.dumps(batch,ensure_ascii=False,indent=2));return 0
        if args.backup:
            from .services import backup
            print(backup(args.db,args.backup));return 0
        if args.diagnose:
            from .services import diagnose
            print(json.dumps(diagnose(args.db),ensure_ascii=False,indent=2));return 0
        if args.stats:
            from .tips import select_draws,validate,default_profile
            scope=default_profile('joker' if args.stats=='joker' else args.game)
            scope.update({'from':args.from_date,'to':args.to_date,'weekday':args.weekday if args.weekday is not None else -1,'kind':args.draw_kind})
            scope=validate(scope)
            if args.stats=='joker' or args.stats=='patterns' and args.game=='joker':
                from .joker_statistics import JokerAnalysis,load_joker
                analysis=JokerAnalysis(select_draws(load_joker(args.db),scope),args.last)
            else:analysis=Analysis(select_draws(load_draws(args.db),scope),0 if args.stats=='periods' else args.last)
            if args.stats=='patterns':
                from .patterns import analyse
                result=analyse(analysis.draws,args.game)
                result.pop('series',None)
            else:result=analysis.report(args.stats)
            result['tables']=[asdict(table) for table in result['tables']]
            if args.stats=='charts':result['chart']=analysis.chart(args.chart,args.stats_number)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        if args.download:
            from .archive_download import load_sources,download_selected
            result=download_selected(load_sources(),args.db)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            if result['errors']: return 1
        creating=bool(args.generate or args.import_csv or args.import_json or args.import_joker_pdf)
        with closing(connect(args.db,create=creating)) as con:
            if args.generate: generate(con)
            if args.import_csv or args.import_json or args.import_joker_pdf:
                path = args.import_csv or args.import_json or args.import_joker_pdf; raw = path.read_bytes()
                records,issues = (parse_joker_csv(raw,path.name) if 'Joker' in path.name else parse_lotto(raw,path.name)) if args.import_csv else parse_joker_pdf(raw,path.name) if args.import_joker_pdf else (json.loads(raw),[])
                print(json.dumps(ingest(con,raw,args.source or str(path),records,issues,args.allow_corrections),ensure_ascii=False))
            if args.summary: print(json.dumps(summary(con),ensure_ascii=False,indent=2))
            if args.check:
                checks=[r[0] for r in con.execute('PRAGMA integrity_check')]; fk=list(con.execute('PRAGMA foreign_key_check'))
                print(json.dumps({'integritaet':checks,'fremdschluessel_fehler':len(fk)}))
                if checks!=['ok'] or fk: return 1
    except Exception as e:
        logging.exception('L001: Aktion fehlgeschlagen; Datenbank: %s',args.db)
        print(f'L001: {e}. Datenbank: {args.db}. Datei, Format und Schreibrechte prüfen; siehe logs/error.log.',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__': sys.exit(main())
