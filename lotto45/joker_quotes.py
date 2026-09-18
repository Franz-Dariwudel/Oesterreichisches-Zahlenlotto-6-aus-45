"""Offizieller Joker-Ergebnisdienst: belegte Quoten, keine abgeleiteten Beträge.

Die öffentliche Schnittstelle wird von der win2day-Ziehungsansicht verwendet.
Sie liefert derzeit einen begrenzten Zeitraum. Die Antwort muss vollständig
sein; eine gekürzte Seite darf nicht als vollständiges Archiv gelten.
"""
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

URL='https://lotterien.win2day.at/jam/drawgame/v1/public/drawResultInfo/joker?limit=5000&offset=0'


def is_url(url):
    parts=urlsplit(url)
    return parts.scheme=='https' and parts.hostname=='lotterien.win2day.at' and parts.path=='/jam/drawgame/v1/public/drawResultInfo/joker'


def integer(value):
    if type(value) is not int or value<0:raise ValueError('L008: Ungültige Joker-Ganzzahl')
    return value


def amount_label(text):
    match=re.fullmatch(r'(?:zu je |zu )?€\s*([0-9.]+),([0-9]{2})',text.strip())
    if not match:raise ValueError('L008: Unbekannter Joker-Eurobetrag')
    return int(match[1].replace('.',''))*100+int(match[2])


def parse_archive(raw):
    """Alle veröffentlichten Ränge prüfen und Originaldetails im Import erhalten."""
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get('game')!='JOKER':raise ValueError('L008: Kein offizielles Joker-Ergebnisformat')
    draws=data.get('drawResults')
    if not isinstance(draws,list) or integer(data.get('maxDrawResultSize'))!=len(draws):
        raise ValueError('L008: Joker-Antwort unvollständig; Quellenadresse und Zeitraum prüfen')
    records=[];dates=set()
    for line,draw in enumerate(draws,1):
        date=dt.date.fromisoformat(draw['drawDate']).isoformat()
        if date in dates:raise ValueError('L008: Mehrdeutiges Joker-Datum')
        dates.add(date)
        if draw.get('payoutReleased') is not True or date<'2000-01-01':continue
        groups=draw['results']
        if len(groups)!=1 or groups[0]['resultType']!='JOKER_NUMBER':raise ValueError('L008: Unbekannte Joker-Zahlenstruktur')
        digits=[integer(v['number']) for v in groups[0]['resultValues']]
        if len(digits)!=6 or any(n>9 for n in digits):raise ValueError('L008: Ungültige Joker-Ziffern')
        ranks=draw['ranks']
        if sorted(r['rankNumber'] for r in ranks)!=list(range(1,7)):raise ValueError('L008: Joker-Gewinnränge unvollständig')
        quotes=[]
        for rank in sorted(ranks,key=lambda r:r['rankNumber']):
            winners=integer(rank['numberOfWinners']);amount=integer(rank['amountPerWinner'])
            label_amount=amount_label(rank['winAmountLabel'])
            status='';kind='je_gewinn'
            if winners==0 and 'jackpot' in rank['description'].lower():
                description=rank['description'].lower().split('jackpot')[0].strip().replace('-',' ')
                prefixes={'':'JP','doppel':'DJP','dreifach':'3JP','vierfach':'4JP','fünffach':'5JP',
                          'sechsfach':'6JP','siebenfach':'7JP','achtfach':'8JP','neunfach':'9JP','zehnfach':'10JP'}
                if description not in prefixes:raise ValueError('L008: Unbekannte Joker-Jackpotstufe')
                status=prefixes[description];kind='jackpot';amount=label_amount
            elif amount!=label_amount:raise ValueError('L008: Widersprüchliche Joker-Beträge')
            quotes.append({'klasse':str(rank['rankNumber']),'regelwerk':'6_rang_pdf','gewinner':winners,
                           'waehrung':'EUR','betrag_hundertstel':amount,'betrag_art':kind,'status':status,
                           'quelle_rang':rank})
        records.append({'spiel':'joker','datum':date,'nummer':''.join(map(str,digits)),
                        'quoten':quotes,'zeile':line})
    if not records:raise ValueError('L008: Keine veröffentlichten Joker-Quoten verfügbar')
    return records,[]


def verified_history():
    """Einzeln belegte Altdaten mit Herkunft erhalten, ohne Archivvollständigkeit zu behaupten."""
    path=Path(__file__).resolve().parent.parent/'resources/joker_quotes_verified.json'
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,list) or not data:raise ValueError('Leere Quotenliste')
        dates=set()
        for item in data:
            url=urlsplit(item['url']);record=item['record']
            if url.scheme!='https' or url.hostname!='www.ots.at' or not url.path.startswith('/presseaussendung/'):
                raise ValueError('Unbekannte Belegquelle')
            date=dt.date.fromisoformat(record['datum']).isoformat()
            if date<'2000-01-01' or date in dates or record['spiel']!='joker':raise ValueError('Ungültiges Joker-Datum')
            dates.add(date)
            quotes=record['quoten']
            if len(quotes) not in (5,6) or [q['klasse'] for q in quotes]!=[str(n) for n in range(1,len(quotes)+1)]:
                raise ValueError('Unvollständige historische Quoten')
            for q in quotes:integer(q['gewinner']);integer(q['betrag_hundertstel'])
        return data
    except (OSError,ValueError,KeyError,TypeError) as error:
        raise ValueError(f'L008: Historische Quotenbelege nicht lesbar: {path}. Programmdateien prüfen. {error}') from error
