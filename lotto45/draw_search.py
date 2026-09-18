"""Kalendergenaue Suche nach Jahr, Jahr/Monat oder Tag, GPL-3.0-only.

Geschlossene ISO-Datumsgrenzen nutzen die vorhandenen Datumsindizes.
Auch Schaltjahre, Monatsenden und das Jahr 9999 sind damit eindeutig.
"""
import calendar
import datetime as dt
import re
from dataclasses import dataclass
from .tip_search import parse_search
from .date_display import format_date


@dataclass(frozen=True)
class DrawPeriod:
    start: str
    end: str
    label: str


def parse_period(text):
    """TT.MM.JJJJ, MM.JJJJ und JJJJ; ältere ISO-/Schrägstricheingaben bleiben gültig."""
    value=text.strip()
    dotted=re.fullmatch(r'(?:(\d{1,2})\.)?(\d{1,2})\.(\d{4})',value,flags=re.ASCII)
    if dotted:
        day,month,year=dotted.groups()
        value=year+'/'+month+('/'+day if day is not None else '')
    match = re.fullmatch(r'([0-9]{4})(?:([/-])([0-9]{1,2})(?:\2([0-9]{1,2}))?)?', value)
    if not match:
        raise ValueError('L002: Jahr, Jahr/Monat oder vollständiges Datum eingeben')
    year, _, month, day = match.groups()
    year = int(year)
    try:
        if month is None:
            start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
            label = f'{year:04d}'
        elif day is None:
            month = int(month)
            start = dt.date(year, month, 1)
            end = dt.date(year, month, calendar.monthrange(year, month)[1])
            label = f'{month:02d}.{year:04d}'
        else:
            start = end = dt.date(year, int(month), int(day))
            label = format_date(start.isoformat())
    except ValueError as error:
        raise ValueError('L002: Ungültiges Kalenderdatum; Jahr, Monat und Tag prüfen') from error
    return DrawPeriod(start.isoformat(), end.isoformat(), label)


@dataclass(frozen=True)
class DateFilter:
    """Vollständiger Zeitraum oder bereits eingegebene Teile eines Datums."""
    period: DrawPeriod
    parts: tuple = ()

    @property
    def label(self):return self.period.label

    def matches(self,date):
        values=(date[8:10],date[5:7],date[:4])
        return all(int(values[index])==int(value) if exact else
                   values[index].startswith(value) or str(int(values[index])).startswith(value)
                   for index,value,exact in self.parts)


def parse_date_filter(text):
    """Live-Suche: erst Tag-Präfix, ab drei Ziffern Jahr; Punkte trennen Tag/Monat/Jahr.

    Ohne Datum darf der Lotto-Zahlenfilter das gesamte Archiv durchsuchen.
    Vollständige Kalenderdaten werden streng geprüft, etwa der 29. Februar.
    """
    value=text.strip()
    if not value:return DateFilter(DrawPeriod('0001-01-01','9999-12-31',''))
    try:return DateFilter(parse_period(value))
    except ValueError:pass
    if re.fullmatch(r'[0-9]{4}([/-])[0-9]{1,2}\1[0-9]{1,2}',value):
        raise ValueError('L002: Ungültiges Kalenderdatum')
    parts=[]
    if re.fullmatch(r'[0-9]{1,3}',value):
        parts=[(2 if len(value)==3 else 0,value,False)]
    elif re.fullmatch(r'[0-9]{1,2}\.[0-9]{0,3}(?:\.[0-9]{0,3})?',value):
        tokens=value.split('.')
        if len(tokens)==2 and len(tokens[1])==3:
            parts=[(1,tokens[0],True),(2,tokens[1],False)]
        else:
            if len(tokens[1])>2:raise ValueError('L002: Ungültiger Monat')
            parts=[(i,token,i<len(tokens)-1) for i,token in enumerate(tokens) if token]
    elif re.fullmatch(r'[0-9]{4}([/-])[0-9]{0,2}(?:\1[0-9]{0,2})?',value):
        tokens=re.split(r'[/-]',value)
        parts=[(index,token,i<len(tokens)-1) for i,(index,token) in enumerate(zip((2,1,0),tokens)) if token]
    else:raise ValueError('L002: Datum als TT.MM.JJJJ, MM.JJJJ oder JJJJ eingeben')
    for index,token,exact in parts:
        maximum=(31,12,9999)[index]
        if exact:
            if not 1<=int(token)<=maximum:raise ValueError('L002: Ungültiger Datumsteil')
        elif index!=2 and not any(str(n).startswith(token) or f'{n:02d}'.startswith(token) for n in range(1,maximum+1)):
            raise ValueError('L002: Ungültiger Datumsteil')
    return DateFilter(DrawPeriod('0001-01-01','9999-12-31',value+'…'),tuple(parts))


def search_live_draws(con,query,numbers=(),game=None):
    """Live-Datumsfilter nach der bestehenden Spiel-/Hauptzahlensuche anwenden."""
    return [row for row in search_draws(con,query.period,numbers,game) if query.matches(row['datum'])]


def parse_draw_numbers(text):
    """Leeres Feld lässt alle Spiele zu; sonst 1–6 verschiedene Lotto-Hauptzahlen."""
    if not text.strip():
        return ()
    query = parse_search(text)
    if query.game != 'lotto':
        raise ValueError('L002: Lotto-Zahlen zwischen 1 und 45 mit Leerzeichen oder Komma trennen')
    return query.numbers


def search_draws(con, period, numbers=(), game=None):
    """Alle gespeicherten Lotto-/Joker-Ziehungen im Zeitraum unverändert lesen.

    Eine Zeitspanne umfasst höchstens ein Jahr. Geladen werden nur Datensätze,
    keine Bilder oder Widgets. Die Oberfläche zeigt die Details seitenweise.
    Gleiches Datum und verschiedene Ziehungskennungen bleiben eigene Treffer.
    Mit Zahlenfilter müssen sämtliche Zahlen unter den sechs Lotto-Hauptzahlen
    vorkommen. Zusatzzahl und Joker gehören nicht zu diesem Lotto-Filter.
    """
    if game not in (None,'lotto','joker'):
        raise ValueError('L002: Unbekanntes Spiel')
    numbers = tuple(numbers)
    if game=='joker' and numbers:
        raise ValueError('L002: Lotto-Zahlenfilter ist im Joker-Archiv nicht verfügbar')
    if numbers and (len(numbers)>6 or any(type(n) is not int or not 1<=n<=45 for n in numbers)
                    or len(set(numbers))!=len(numbers)):
        raise ValueError('L002: Eine bis sechs verschiedene Lotto-Zahlen von 1 bis 45 erforderlich')
    rows = []
    for game in ((game,) if game else ('lotto',) if numbers else ('lotto', 'joker')):
        sql = f'SELECT d.* FROM {game}_ziehungen d'
        if numbers:
            sql += ' JOIN lotto_tipps t ON t.id=d.tipp_id'
        sql += ' WHERE d.datum BETWEEN ? AND ?'
        if numbers:
            sql += ' AND ' + ' AND '.join('? IN(t.n1,t.n2,t.n3,t.n4,t.n5,t.n6)' for _ in numbers)
        cursor = con.execute(sql, (period.start, period.end, *numbers))
        columns = [column[0] for column in cursor.description]
        rows.extend({'spiel': game, **dict(zip(columns, row))} for row in cursor)
    return sorted(rows, key=lambda row: (row['datum'], row['spiel'] == 'lotto', row['kennung'], row['id']), reverse=True)
