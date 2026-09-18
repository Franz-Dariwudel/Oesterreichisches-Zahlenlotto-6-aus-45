"""Teilzahlensuche in gezogenen Kombinationen, GPL-3.0-only.

Alle eingegebenen Lotto-Zahlen müssen im Tipp vorkommen, unabhängig von
ihrer Position. Seiten begrenzen nur die gleichzeitig geladenen Zeilen;
die Gesamtzahl und die letzte Seite berücksichtigen sämtliche Treffer.
Die Oberfläche berücksichtigt nur gezogene Kombinationen. Die vollständigen
Tippkataloge bleiben unverändert; interne Katalogabfragen sind ausdrücklich optional.
"""
import math
import re
from dataclasses import dataclass
from functools import lru_cache

from .database import tip_id


@dataclass(frozen=True)
class SearchQuery:
    game: str
    numbers: tuple = ()
    joker: str = ''

    @property
    def expected(self):
        return joker_matches(self.joker) if self.game == 'joker' else math.comb(45-len(self.numbers), 6-len(self.numbers))


@lru_cache(maxsize=128)
def joker_matches(pattern):
    """Anzahl sechsstelliger Nummern mit Teilfolge, einschließlich Überlappungen.

    Pro Stelle nur passende Präfixzustände zählen; keine Million Nummern erzeugen.
    Ein bereits gefundener Treffer bleibt bei weiteren Ziffern erhalten.
    """
    states={'':1}
    for _ in range(6):
        following={}
        for prefix,count in states.items():
            for digit in '0123456789':
                candidate=prefix+digit
                if prefix==pattern or candidate.endswith(pattern):key=pattern
                else:key=next((pattern[:n] for n in range(len(pattern)-1,0,-1) if candidate.endswith(pattern[:n])),'')
                following[key]=following.get(key,0)+count
        states=following
    return states.get(pattern,0)


def parse_search(text,game=None):
    """Optional auf das gewählte Spiel beschränken; ohne Auswahl beide erkennen."""
    if game not in (None,'lotto','joker'):
        raise ValueError('L002: Unbekanntes Spiel')
    value = text.strip()
    if game!='lotto' and re.fullmatch(r'[0-9]{6}', value):
        return SearchQuery('joker', joker=value)
    if game=='joker':
        if re.fullmatch(r'[0-9]{1,6}',value):return SearchQuery('joker',joker=value)
        raise ValueError('L002: Eine bis sechs Joker-Ziffern eingeben')
    parts = value.replace(',', ' ').split()
    if not 1 <= len(parts) <= 6 or any(not re.fullmatch(r'[0-9]{1,2}', p) for p in parts):
        raise ValueError('L002: Eine bis sechs Lotto-Zahlen von 1 bis 45 oder sechs Joker-Ziffern eingeben')
    numbers = tuple(sorted(int(p) for p in parts))
    if len(set(numbers)) != len(numbers) or not 1 <= numbers[0] <= numbers[-1] <= 45:
        raise ValueError('L002: Lotto-Zahlen müssen verschieden sein und zwischen 1 und 45 liegen')
    return SearchQuery('lotto', numbers=numbers)


def search_tips(con, query, page=0, page_size=100,*,drawn_only=True):
    """Eine Seite mit Gesamtzahl und allen zugehörigen Ziehungsdaten lesen.

    Die Abfrage verändert weder Tippkatalog noch Ziehungen. Die vorhandene
    Verbindung gehört dem Aufrufer, bei GTK jeweils einem Hintergrundthread.
    Sortierung nach stabiler Katalog-ID verhindert doppelte Seitengrenzen.
    """
    if type(page) is not int or page < 0 or type(page_size) is not int or not 1 <= page_size <= 500:
        raise ValueError('L002: Ungültige Ergebnisseite')
    if query.game == 'joker':
        where, params, columns, key = ('nummer=?' if len(query.joker)==6 else 'instr(nummer,?)>0'), (query.joker,), 'nummer', 'nummer'
    elif len(query.numbers) == 6:
        where, params, columns, key = 'id=?', (tip_id(query.numbers),), 'id,n1,n2,n3,n4,n5,n6', 'id'
    else:
        where = ' AND '.join('? IN(n1,n2,n3,n4,n5,n6)' for _ in query.numbers)
        params, columns, key = query.numbers, 'id,n1,n2,n3,n4,n5,n6', 'id'
    table = query.game + '_tipps'
    if drawn_only:
        draw_key='nummer' if query.game=='joker' else 'tipp_id'
        # Die kurze Liste gezogener IDs verhindert einen Scan aller 8 Mio. Tipps.
        where+=f' AND {key} IN (SELECT DISTINCT {draw_key} FROM {query.game}_ziehungen)'
    total = con.execute(f'SELECT count(*) FROM {table} WHERE {where}', params).fetchone()[0]
    pages = max(1, math.ceil(total/page_size))
    page = min(page, pages-1)
    tips = list(con.execute(f'SELECT {columns} FROM {table} WHERE {where} ORDER BY {key} LIMIT ? OFFSET ?',
                            (*params, page_size, page*page_size)))
    dates = {row[0]: [] for row in tips}
    if tips:
        draw_key = 'nummer' if query.game == 'joker' else 'tipp_id'
        placeholders = ','.join('?' for _ in tips)
        for ident, date, kind in con.execute(
                f'SELECT {draw_key},datum,kennung FROM {query.game}_ziehungen '
                f'WHERE {draw_key} IN ({placeholders}) ORDER BY datum,kennung', tuple(dates)):
            dates[ident].append(date + (f' · {kind}' if kind != 'haupt' else ''))
    return {'total': total, 'expected': total if drawn_only else query.expected, 'page': page, 'pages': pages,
            'first': page*page_size+1 if total else 0, 'last': page*page_size+len(tips),
            'rows': [{'tip': row[0] if query.game == 'joker' else tuple(row[1:]),
                      'dates': dates[row[0]]} for row in tips]}
