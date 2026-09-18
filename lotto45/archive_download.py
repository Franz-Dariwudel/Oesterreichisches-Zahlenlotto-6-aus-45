"""Auswählbare Archiv-Webseiten und Download mit anschließendem Datenimport.

Die Quellenliste ist unabhängig von den Spracheinstellungen gespeichert.
HTML-Seiten werden ausschließlich nach bekannten Archivdateien durchsucht;
Seitencode wird nicht ausgeführt. Originaldateien bleiben in der Datenbank,
Arbeitsdateien werden in eigenen gesperrten /tmp-Unterordnern abgelegt.
GPL-3.0-only · Josef Lehner.
"""
from contextlib import closing
from copy import deepcopy
from html.parser import HTMLParser
import json
import hashlib
import logging
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .database import connect, ingest
from .importers import parse_lotto, parse_joker_csv, parse_joker_pdf
from .settings import ROOT, download_directory
from . import joker_history,joker_quotes
from .schema import now
from .tempwork import workspace

try:
    DEFAULT_SOURCES = json.loads((ROOT/'resources/default_sources.json').read_text(encoding='utf-8'))
    if not isinstance(DEFAULT_SOURCES,list):raise ValueError('Liste erwartet')
except (OSError,ValueError) as error:
    logging.error('L007: Standardquellen fehlen oder sind ungültig: %s. resources/default_sources.json wiederherstellen.',error)
    DEFAULT_SOURCES=[]


def validate_url(value):
    """Nur vollständige öffentliche HTTP(S)-Adressen ohne eingebettete Anmeldung."""
    if not isinstance(value, str) or any(c.isspace() or ord(c)<32 for c in value):
        raise ValueError('L007: Ungültige Webadresse; vollständige HTTP(S)-Adresse eintragen.')
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            raise ValueError
        parts.port
    except ValueError:
        raise ValueError('L007: Ungültige Webadresse; vollständige HTTP(S)-Adresse ohne Anmeldedaten eintragen.') from None
    return urlunsplit(parts._replace(fragment=''))


def validate_sources(value):
    if not isinstance(value, list):
        raise ValueError('L007: Quellenliste muss eine Liste sein; config/download_sources.json prüfen.')
    result, seen = [], set()
    for source in value:
        if not isinstance(source, dict) or not isinstance(source.get('name'), str) or not source['name'].strip() or type(source.get('enabled')) is not bool:
            raise ValueError('L007: Quellen benötigen einen Namen, eine Webadresse und eine Auswahlmarkierung.')
        if source.get('game','auto') not in ('auto','lotto','joker') or source.get('format','auto') not in ('auto','csv','pdf','json','html'):
            raise ValueError('L007: Unbekanntes Spiel oder Quellenformat.')
        if type(source.get('priority',50)) is not int or not 0<=source.get('priority',50)<=999:raise ValueError('L007: Priorität 0–999 erforderlich.')
        url = validate_url(source.get('url'))
        if url in seen:
            raise ValueError('L007: Diese Webadresse ist bereits eingetragen.')
        seen.add(url)
        result.append({**source, 'name': source['name'].strip(), 'url': url})
    return result


def load_sources(root=ROOT):
    path = root/'config/download_sources.json'
    if not path.exists():
        return deepcopy(DEFAULT_SOURCES)
    try:
        return validate_sources(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError) as error:
        raise ValueError(f'L007: Quellenliste nicht lesbar: {path}. Datei prüfen. {error}') from error


def save_sources(value, root=ROOT):
    """Validierte Liste atomar speichern; andere Einstellungen nicht verändern."""
    sources = validate_sources(value)
    folder = root/'config'
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, prefix='download-sources-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(sources, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        temporary.replace(folder/'download_sources.json')
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return sources


def fetch_url(url):
    if joker_history.is_url(url):return joker_history.fetch_archive(url)
    request = Request(validate_url(url), headers={'User-Agent': '6aus45 archive downloader'})
    with urlopen(request, timeout=30) as response:
        validate_url(response.url)
        raw = response.read(25_000_001)
        if len(raw)>25_000_000:
            raise ValueError('L008: Archivdatei größer als 25 MB; Download abgebrochen.')
        length=response.headers.get('Content-Length')
        if length and int(length)!=len(raw):raise ValueError('L008: Unvollständiger Download.')
        if not raw:raise ValueError('L008: Leere Download-Datei.')
        return raw


def filename(url):
    return Path(unquote(urlsplit(url).path)).name


def archive_type(name):
    """Ein neuer Anbieter kann bekannte CSV/PDF-Formate oder das JSON-Schema liefern."""
    if re.fullmatch(r'.+\.json', name, re.I): return 'json'
    if name.lower()=='results.csv':return 'lotto_simple_csv'
    if re.fullmatch(r'.*Joker_\d{4}\.csv', name, re.I): return 'joker_csv'
    if re.fullmatch(r'.*Joker_\d{4}\.pdf', name, re.I): return 'joker_pdf'
    if re.fullmatch(r'.*Lotto_\d{4}\.csv', name, re.I) or name.lower() in ('1986-2010-lotto.csv', 'lotto-ziehungen-2010-2017.csv'):
        return 'lotto_csv'
    return None


class ArchiveLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower()=='a':
            href = dict(attrs).get('href')
            if href: self.links.append(href)


def discover_archives(raw, page, preferred=None):
    parser = ArchiveLinks()
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: text = raw.decode('cp1252')
    parser.feed(text)
    candidates = {}
    for href in parser.links:
        try: url = validate_url(urljoin(page, href))
        except ValueError: continue
        name = filename(url)
        if archive_type(name): candidates.setdefault(name.lower(), url)
    # Jahres-CSV vor gleichnamigem PDF bevorzugen: dieselben Daten nur einmal laden.
    for name in list(candidates):
        if preferred!='pdf' and name.endswith('.pdf') and name[:-4]+'.csv' in candidates:
            del candidates[name]
    if preferred in ('csv','pdf','json'):
        candidates={name:url for name,url in candidates.items() if name.endswith('.'+preferred)}
    # Die offizielle Übersichtsseite zeigt nur die jüngsten Jahrgänge.
    # Ältere Jahresdateien ab 2017 bleiben unter ihren bestätigten URLs abrufbar.
    parts=urlsplit(page)
    years=[int(m[1]) for name in candidates if (m:=re.fullmatch(r'NN_W2D_STAT_Joker_(\d{4})\.csv',name,re.I))]
    if parts.hostname in ('www.win2day.at','win2day.at') and parts.path=='/lotterie/joker-statistik' and years:
        for year in range(2017,min(years)):
            name=f'NN_W2D_STAT_Joker_{year}.csv'
            candidates.setdefault(name.lower(),'https://statics.win2day.at/media/'+name)
    def order(url):
        name = filename(url)
        year = re.search(r'\d{4}', name)
        return (int(year[0]) if year else 9999, name.lower())
    return sorted(candidates.values(), key=order)


def parse_archive(raw, name, source=None):
    if source and joker_history.is_url(source):return joker_history.parse_archive(raw)
    kind = archive_type(name)
    # Jahresinformationen für vorhandene Parser einheitlich schreiben.
    name = re.sub('joker_', 'Joker_', name, flags=re.I)
    name = re.sub('lotto_', 'Lotto_', name, flags=re.I)
    if kind=='joker_csv': return parse_joker_csv(raw, name)
    if kind=='joker_pdf': return parse_joker_pdf(raw, name)
    if kind=='lotto_csv': return parse_lotto(raw, name)
    if kind=='lotto_simple_csv':return parse_simple_lotto(raw)
    if kind=='json':
        records = json.loads(raw)
        if not isinstance(records, list) or not records or any(not isinstance(r, dict) for r in records):
            raise ValueError('L008: JSON-Datei muss eine nicht leere Liste von Ziehungen enthalten.')
        return records, []
    raise ValueError('L008: Archivformat nicht unterstützt; bekannte Lotto-/Joker-Datei oder Ziehungs-JSON verwenden.')


def parse_simple_lotto(raw):
    """CSV von lottery-archive: ISO-Datum, sechs Zahlen und Zusatzzahl, keine Quoten.

    Format streng erkennen: Eine fremde results.csv darf nicht als Lotto-Datei
    fehlinterpretiert werden. Originalbytes werden vom normalen Import erhalten.
    """
    import csv,io,datetime
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    fields=['date',*(f'n{i}' for i in range(1,7)),'zusatzzahl']
    if reader.fieldnames!=fields:raise ValueError('L008: Unerwartete CSV-Spalten; Datum, sechs Zahlen und Zusatzzahl erforderlich.')
    records=[];dates=set()
    for row in reader:
        if None in row or any(v is None for v in row.values()):raise ValueError('L008: Unvollständige CSV-Zeile')
        date=datetime.date.fromisoformat(row['date']).isoformat()
        if date in dates:raise ValueError('L008: Mehrdeutige doppelte Ziehung in CSV')
        dates.add(date)
        if any(not row[k].isascii() or not row[k].isdigit() for k in fields[1:]):raise ValueError('L008: Ungültige Lottozahl')
        numbers=[int(row[f'n{i}']) for i in range(1,7)];bonus=int(row['zusatzzahl'])
        if len(set(numbers))!=6 or any(not 1<=n<=45 for n in [*numbers,bonus]) or bonus in numbers:
            raise ValueError('L008: Ungültige Haupt- oder Zusatzzahlen')
        records.append({'spiel':'lotto','datum':date,'zahlen':sorted(numbers),'zusatzzahl':bonus,'zeile':reader.line_num})
    if not records:raise ValueError('L008: Keine Lotto-Ziehungen in CSV')
    return records,[]


def download_selected(sources, db, download_dir=None, fetch=fetch_url, progress=lambda event, value: None, cancel=None):
    """Nur angehakte Quellen laden; Fehler je Datei melden, erfolgreiches behalten.

    Ein Import bleibt eine atomare Datenbankaktion. Fehlgeschlagene Dateien
    werden nie als erfolgreicher Download/Import gezählt. Der Ergebnisbericht
    unterscheidet neue Quellen, unveränderte Quellen und Prüfhinweise.
    """
    configured=validate_sources(sources)
    selected = [s for s in configured if s['enabled']]
    if not selected:
        raise ValueError('L007: Keine Quelle ausgewählt; mindestens eine Webseite markieren.')
    folder = Path(download_dir) if download_dir is not None else Path('/tmp')
    folder.mkdir(parents=True, exist_ok=True)
    result = {'sources': len(selected), 'files': [], 'errors': []}
    visited = set()

    def failure(url, error):
        message = f'L008: {error}'
        result['errors'].append({'url': url, 'message': message})
        logging.warning('L008: Archivdownload fehlgeschlagen (%s): %s', filename(url), type(error).__name__)
        progress('error', url)

    def cancelled():
        if cancel is not None and cancel.is_set():raise InterruptedError('L013: Datencheck abgebrochen.')

    with workspace(folder) as temporary:
        with closing(connect(db)) as con:
            with con:
                con.execute('UPDATE data_source SET enabled=0')
                for item in configured:
                    con.execute('INSERT INTO data_source(url,name,game,format,priority,enabled) VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET name=excluded.name,game=excluded.game,format=excluded.format,priority=excluded.priority,enabled=excluded.enabled',
                        (item['url'],item['name'],item.get('game','auto'),item.get('format','auto'),item.get('priority',50),int(item['enabled'])))
            with con:
                con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('last_data_check',now()))
            for source in sorted(selected,key=lambda s:s.get('priority',50)):
                cancelled()
                with con:
                    con.execute('INSERT INTO data_source(url,name,game,format,priority,enabled,checked) VALUES(?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET name=excluded.name,game=excluded.game,format=excluded.format,priority=excluded.priority,enabled=excluded.enabled,checked=excluded.checked',
                        (source['url'],source['name'],source.get('game','auto'),source.get('format','auto'),source.get('priority',50),int(source['enabled']),now()))
                page = source['url']
                progress('source', source['name'])
                try:
                    if archive_type(filename(page)) or joker_history.is_url(page) or joker_quotes.is_url(page):
                        urls = [page]
                    else:
                        urls = discover_archives(fetch(page), page,source.get('format'))
                        if not urls:
                            raise ValueError('Keine unterstützten Archivlinks auf dieser Webseite gefunden. Direkten Archivlink oder andere Seite eintragen.')
                except InterruptedError:raise
                except Exception as error:
                    with con:
                        con.execute('INSERT INTO import_run(started,url,status,details) VALUES(?,?,?,?)',(now(),page,'error',str(error)))
                        con.execute('UPDATE data_source SET status=? WHERE url=?',('error',page))
                    failure(page, error)
                    continue
                source_failed=False
                for url in urls:
                    cancelled()
                    if url in visited: continue
                    visited.add(url)
                    name = filename(url)
                    progress('file', name)
                    raw=None
                    try:
                        raw = conditional_fetch(con,url) if fetch is fetch_url else fetch(url)
                        cancelled()
                        staged = Path(temporary)/f'{len(visited):04d}-{name}'
                        staged.write_bytes(raw)
                        digest=hashlib.sha256(raw).hexdigest()
                        known=con.execute('SELECT id FROM import_quellen WHERE sha256=?',(digest,)).fetchone()
                        if known:
                            result['files'].append({'url':url,'name':name,'bereits_importiert':True,'quelle':known[0]})
                            with con:con.execute('INSERT INTO import_run(started,url,sha256,status,details) VALUES(?,?,?,?,?)',(now(),url,digest,'unchanged','Identische Quelldatei'))
                            continue
                        expected=source.get('format','auto')
                        actual=archive_type(name)
                        if expected in ('csv','pdf','json') and not (actual and actual.endswith(expected)) and not (expected=='json' and joker_quotes.is_url(url)):
                            raise ValueError('L008: Erwartetes Format '+expected+' passt nicht zur Quelldatei '+name)
                        records, issues = joker_quotes.parse_archive(staged.read_bytes()) if joker_quotes.is_url(url) else parse_archive(staged.read_bytes(), name, url)
                        if source.get('game','auto')!='auto' and any(r['spiel']!=source['game'] for r in records):raise ValueError('L008: Quelldaten gehören zu einem anderen Spiel.')
                        critical=[message for _,message,_ in issues if any(word in message for word in ('Ungültige','invalid literal','Quote nicht lesbar','Datum der Folgezeile'))]
                        if critical:raise ValueError('L008: Kritischer Parserfehler; Datei nicht übernommen: '+critical[0])
                        imported=None
                        if joker_history.is_url(url):
                            previous=con.execute('SELECT id,original FROM import_quellen WHERE uri=? ORDER BY id DESC LIMIT 1',(url,)).fetchone()
                            if previous:
                                try:old_records,old_issues=joker_history.parse_archive(previous['original'])
                                except (ValueError,UnicodeError):pass
                                else:
                                    if joker_history.content_key(records,issues)==joker_history.content_key(old_records,old_issues):
                                        imported={'bereits_importiert':True,'quelle':previous['id']}
                        if imported is None:imported = ingest(con, raw, url, records, issues,fill_missing_only=joker_quotes.is_url(url))
                        result['files'].append({'url': url, 'name': name, **imported})
                        if joker_quotes.is_url(url):
                            for evidence in joker_quotes.verified_history():
                                record=evidence['record'];origin=evidence['url']
                                excerpt=json.dumps(evidence,ensure_ascii=False,sort_keys=True).encode('utf-8')
                                imported=ingest(con,excerpt,origin,[record],fill_missing_only=True)
                                result['files'].append({'url':origin,'name':'Joker '+record['datum'],**imported})
                    except InterruptedError:raise
                    except Exception as error:
                        if raw is not None:
                            try:
                                rejected=Path(db).parent/'rejected';rejected.mkdir(exist_ok=True)
                                preserved=rejected/(hashlib.sha256(raw).hexdigest()+'.bin')
                                if not preserved.exists():preserved.write_bytes(raw)
                            except OSError as preserve_error:
                                logging.error('L008: Abgewiesene Rohdatei konnte nicht gesichert werden: %s',preserve_error)
                                error=ValueError(str(error)+'; Rohdatei konnte nicht gesichert werden: '+str(preserve_error))
                        source_failed=True
                        with con:con.execute('INSERT INTO import_run(started,url,status,details) VALUES(?,?,?,?)',(now(),url,'error',str(error)))
                        failure(url, error)
                with con:
                    con.execute('UPDATE data_source SET status=?,last_success=CASE WHEN ? THEN last_success ELSE ? END WHERE url=?',('error' if source_failed else 'success',int(source_failed),now(),page))
            with con:
                con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('internet','error' if result['errors'] else 'online'))
                if not result['errors']:con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('last_update',now()))
    return result


def probe_sources(sources,fetch=fetch_url,cancel=None):
    """Erreichbarkeit UND Struktur prüfen; keine Ziehungen importieren."""
    result=[]
    for source in validate_sources(sources):
        if not source['enabled']:continue
        if cancel and cancel.is_set():raise InterruptedError('L013: Quellenprüfung abgebrochen.')
        try:
            raw=fetch(source['url'])
            if len(raw)<20:raise ValueError('Datei zu klein oder leer')
            name=filename(source['url'])
            if joker_quotes.is_url(source['url']):records,_=joker_quotes.parse_archive(raw)
            elif archive_type(name) or joker_history.is_url(source['url']):records,_=parse_archive(raw,name,source['url'])
            else:
                urls=discover_archives(raw,source['url'])
                if not urls:raise ValueError('Keine unterstützten Archivlinks gefunden')
                url=urls[-1];records,_=parse_archive(fetch(url),filename(url),url)
            if not records:raise ValueError('Keine gültigen Ziehungen gefunden')
            result.append({'name':source['name'],'status':'OK','records':len(records)})
        except Exception as error:result.append({'name':source['name'],'status':'L008: '+str(error),'records':0})
    return result


def conditional_fetch(con,url):
    """HTTP-Validatoren verwenden; 304 liest die geprüften Originalbytes der DB."""
    from urllib.error import HTTPError
    if joker_history.is_url(url):return fetch_url(url)
    previous=con.execute('SELECT * FROM source_cache WHERE url=?',(url,)).fetchone()
    headers={'User-Agent':'6aus45 archive downloader'}
    if previous:
        if previous['etag']:headers['If-None-Match']=previous['etag']
        if previous['modified']:headers['If-Modified-Since']=previous['modified']
    try:
        with urlopen(Request(validate_url(url),headers=headers),timeout=30) as response:
            validate_url(response.url);raw=response.read(25000001)
            if not raw or len(raw)>25000000:raise ValueError('L008: Leere oder zu große Quelldatei.')
            length=response.headers.get('Content-Length')
            if length and int(length)!=len(raw):raise ValueError('L008: Unvollständiger Download.')
            # Validatoren nur zusammen mit bereits erfolgreich importierten Bytes merken.
            digest=hashlib.sha256(raw).hexdigest()
            if con.execute('SELECT 1 FROM import_quellen WHERE sha256=?',(digest,)).fetchone():
                with con:con.execute('INSERT OR REPLACE INTO source_cache VALUES(?,?,?,?)',(url,response.headers.get('ETag'),response.headers.get('Last-Modified'),digest))
            return raw
    except HTTPError as error:
        if error.code!=304 or not previous:raise
        row=con.execute('SELECT original FROM import_quellen WHERE sha256=?',(previous['sha256'],)).fetchone()
        if not row:raise ValueError('L008: HTTP-Cache ohne Archivquelle; Quelle erneut prüfen.')
        return row[0]


def ensure_standard_sources(root=ROOT):
    """Fehlende Standards ergänzen; bestehende Auswahl/URL-Overrides erhalten."""
    path=root/'config/download_sources.json'
    if not path.exists():save_sources(DEFAULT_SOURCES,root);return
    sources=load_sources(root);names={s['name'] for s in sources};urls={s['url'] for s in sources}
    additions=[{**s,'enabled':False} for s in DEFAULT_SOURCES if s['name'] not in names and s['url'] not in urls]
    if additions:save_sources(sources+additions,root)
