"""Historische Joker-Zahlen aus dem öffentlichen Archiv von Norbert M. Säumel.

Die Archivsuche speichert ihren Zeitraum in einer Sitzung. Deshalb zuerst die
Formularseite lesen, dann mit denselben Sitzungscookies den gesamten Zeitraum
anfordern. Keine Anmeldung, kein Seitencode und keine abgeschaltete TLS-Prüfung.
Original-HTML wird vom normalen Import archiviert; fehlende Quoten bleiben leer.
"""
from collections import Counter
import datetime as dt
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import json
import re
from urllib.parse import urlencode,urljoin,urlsplit
from urllib.request import build_opener,HTTPCookieProcessor,Request

URL='http://mathematik.norbertsaeumel.at/serie/joker/statistik.php'
FORM='http://mathematik.norbertsaeumel.at/serie/joker/archivsuche.php'
MAX_BYTES=25_000_000


def is_url(url):
    parts=urlsplit(url)
    return (parts.scheme in ('http','https') and parts.hostname=='mathematik.norbertsaeumel.at'
            and parts.path=='/serie/joker/statistik.php' and not parts.query)


class ArchiveHTML(HTMLParser):
    """Nur Text, Tabellen und die beiden Datumsfelder lesen."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.text=[];self.inputs={};self.action=None;self.row=None;self.cell=None;self.line=0

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='form':self.action=attrs.get('action')
        elif tag=='input' and attrs.get('name') in ('jokerziehungendatumbeginn','jokerziehungendatumende'):
            self.inputs[attrs['name']]=attrs
        elif tag=='tr':self.row=[];self.line=self.getpos()[0]
        elif tag in ('td','th'):self.cell=[]

    def handle_data(self,data):
        self.text.append(data)
        if self.cell is not None:self.cell.append(data)

    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None:self.row.append(' '.join(''.join(self.cell).split()))
            self.cell=None
        elif tag=='tr' and self.row is not None:
            self.rows.append((self.line,self.row));self.row=None


def html(raw):
    parser=ArchiveHTML();parser.feed(raw.decode('utf-8-sig'));parser.close();return parser


def fetch_archive(url):
    """Begrenzte öffentliche Formularabfrage; Cookies nur für diesen Download behalten."""
    if not is_url(url):raise ValueError('L008: Unbekannte Joker-Archivseite')
    opener=build_opener(HTTPCookieProcessor(CookieJar()))
    def read(request):
        with opener.open(request,timeout=30) as response:
            parts=urlsplit(response.url)
            if parts.hostname!=urlsplit(url).hostname or parts.scheme!=urlsplit(url).scheme:
                raise ValueError('L008: Unerwartete Weiterleitung des Joker-Archivs')
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError('L008: Joker-Archiv größer als 25 MB')
            return raw
    headers={'User-Agent':'6aus45 archive downloader'}
    page=html(read(Request(url,headers=headers)))
    action=urljoin(url,page.action or '')
    if action!=FORM:raise ValueError('L008: Joker-Archivformular wurde geändert')
    try:
        begin=page.inputs['jokerziehungendatumbeginn']['min']
        end=page.inputs['jokerziehungendatumende']['max']
        if begin!='1988-10-02' or not dt.date.fromisoformat(begin)<=dt.date.fromisoformat(end)<=dt.date.today():raise ValueError()
    except (KeyError,ValueError) as error:
        raise ValueError('L008: Zeitraum des Joker-Archivs fehlt oder ist ungültig') from error
    data=urlencode({'jokerziehungendatumbeginn':begin,'jokerziehungendatumende':end,'Send':'Senden'}).encode('ascii')
    return read(Request(action,data=data,headers=headers))


def parse_archive(raw):
    """Datumswerte/Ziffern streng prüfen; widersprüchliche Doppeldaten auslassen."""
    page=html(raw);text=' '.join(' '.join(page.text).split())
    count=re.search(r'Das Archiv umfasst.*?bis zur\s+([0-9.]+)\.\s+Ziehung',text)
    if not count or not page.rows or page.rows[0][1]!=['Ziehungsdatum','Jokerzahl']:
        raise ValueError('L008: Joker-Archivkopf nicht erkannt')
    rows=page.rows[1:]
    if len(rows)!=int(count[1].replace('.','')):
        raise ValueError('L008: Joker-Archiv unvollständig; vollständigen Zeitraum ab 1988 anfordern')
    months={name:i for i,name in enumerate(('Jänner','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'),1)}
    months['Januar']=1
    days=('Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag')
    parsed=[];issues=[]
    for line,row in rows:
        try:
            match=re.fullmatch(r'(\w+),\s+(\d{2})\.\s+(\w+)\s+(\d{4})',row[0])
            if len(row)!=7 or not match:raise ValueError('Unerwartete Archivspalten oder Datum')
            date=dt.date(int(match[4]),months[match[3]],int(match[2]))
            if match[1]!=days[date.weekday()] or not dt.date(1988,10,2)<=date<=dt.date.today():
                raise ValueError('Ungültiges Ziehungsdatum oder Wochentag')
            if any(not re.fullmatch('[0-9]',digit) for digit in row[1:]):raise ValueError('Ungültige Jokerziffer')
            parsed.append(({'spiel':'joker','datum':date.isoformat(),'nummer':''.join(row[1:]),'zeile':line},row))
        except (ValueError,KeyError,IndexError) as error:issues.append((line,'L003: '+str(error),row))
    counts=Counter(record['datum'] for record,_ in parsed)
    records=[]
    for record,row in parsed:
        if counts[record['datum']]>1:
            issues.append((record['zeile'],'L003: Mehrdeutiges doppeltes Joker-Datum im Zusatzarchiv; Zeile nicht übernommen',row))
        else:records.append(record)
    if not records:raise ValueError('L008: Keine eindeutigen Joker-Ziehungen im Archiv')
    return records,issues


def content_key(records,issues):
    """Die laufende Website-Uhr ist kein neuer Ziehungsstand; Originale erhalten."""
    return json.dumps((sorted((r['datum'],r['nummer']) for r in records),
                       sorted((message,row) for _,message,row in issues)),ensure_ascii=False)
