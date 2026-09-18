"""Import der drei offiziellen CSV-Archivformate; unbekannte Zeilen bleiben prüfbar."""
import csv
import datetime as dt
from decimal import Decimal
import re
from .database import tip_id


def quote(label, winners, amount, currency, rule):
    winners, amount = winners.strip(), amount.strip()
    count = int(winners.replace('.','')) if re.fullmatch(r'[0-9.]+',winners) else None
    jackpot = 'JP' in winners.upper() or 'JACKPOT' in winners.upper()
    value = Decimal(re.sub(r'\s+', '', amount).replace('.','').replace(',','.')) * 100 if amount else None
    if value is not None and value != value.to_integral_value(): raise ValueError('Mehr als zwei Nachkommastellen')
    return {'klasse':label.replace(' ',''),'regelwerk':rule,'gewinner':0 if jackpot else count,
            'waehrung':currency,'betrag_hundertstel':int(value) if value is not None else None,
            'betrag_art':'jackpot' if jackpot else 'je_gewinn' if count is not None and count > 0 else 'unbekannt',
            'status':winners if count is None else '', 'roh_gewinner':winners,'roh_betrag':amount}


def parse_lotto(raw, filename):
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: text = raw.decode('cp1252')
    rows = list(csv.reader(text.splitlines(),delimiter=';'))
    yearly = re.search(r'Lotto_(\d{4})',filename)
    year, currency = (int(yearly[1]),'EUR') if yearly else (None,None)
    middle = not yearly and '2010-2017' in filename
    records, issues = [], []
    current = None
    for lineno, original in enumerate(rows,1):
        row = [x.strip() for x in original] + ['']*40
        title = re.search(r'(\d{4}) Lotto.*(ATS|EUR)',row[0])
        if title:
            year,currency = int(title[1]),title[2]; current=None; continue
        if not any(row): continue
        date_col = 0 if yearly else 1
        primary = bool(re.fullmatch(r'\d{1,2}\.\d{1,2}\.(?:\d{4})?',row[date_col])) and (not yearly or row[1])
        secondary = (middle and row[2].lower()=='gezogen') or (yearly and not row[1] and bool(row[10]))
        try:
            if primary:
                day,month,*_ = row[date_col].split('.')
                date = dt.date(year,int(month),int(day)).isoformat()
                offset = 2 if not middle else 3
                ns = [int(x) for x in row[offset:offset+6]]
                bonus = int(row[offset+7]); tip_id(ns)
                if bonus in ns or bonus not in range(1,46): raise ValueError('Ungültige Zusatzzahl')
                current = {'spiel':'lotto','datum':date,'zahlen':sorted(ns),'zusatzzahl':bonus,'zeile':lineno,'quoten':[]}
                records.append(current)
                if not yearly and not middle:
                    order = [int(x) for x in row[25:31] if x.isdigit()]
                    if sorted(order)==sorted(ns) and row[32].isdigit() and int(row[32])==bonus: current['reihenfolge']=order
                    else: issues.append((lineno,'L003: Originalreihenfolge oder ZZ weicht ab',original))
            elif not secondary:
                if any('Datum' in x or 'Anzahl' in x or 'Reihenfolge' in x or 'Sechser' in x for x in row): continue
                issues.append((lineno,'L003: Nicht zugeordnete Archivzeile',original)); continue
            if current is None: raise ValueError('Folgezeile ohne Ziehung')
            if secondary and middle:
                order = [int(x) for x in row[3:9]]
                if sorted(order)==current['zahlen'] and int(row[10])==current['zusatzzahl']: current['reihenfolge']=order
                else: issues.append((lineno,'L003: Originalreihenfolge oder ZZ weicht ab',original))
            if secondary and yearly and row[0]:
                d,m,*_ = row[0].split('.')
                if dt.date(year,int(m),int(d)).isoformat()!=current['datum']: raise ValueError('Datum der Folgezeile weicht ab')
            if not yearly and not middle:
                groups = [(label,row[i],row[i+2]) for label,i in zip(['6er','5er+ZZ','5er','4er','3er'],range(10,25,3))]
                rule = '5_rang'
            else:
                start = 10 if yearly else 11
                groups = [(row[i],row[i+1],row[i+3]) for i in range(start,start+16,4) if row[i]]
                rule = '8_rang'
            for label,winners,amount in groups:
                try: current['quoten'].append(quote(label,winners,amount,currency,rule))
                except (ValueError,ArithmeticError) as e: issues.append((lineno,f'L003: Quote nicht lesbar: {e}',original))
        except (ValueError,TypeError,IndexError) as e:
            issues.append((lineno,f'L003: {e}',original))
            if primary: current = None
    if not records: raise ValueError('L003: Keine Lotto-Ziehungen erkannt')
    return records,issues


def parse_joker_pdf(raw, filename):
    """Offizielle Jahres-PDFs: Rang 2–6 liefern Gewinnerzahlen, keine Beträge.

    Fehlende Quoten werden NULL, niemals null Euro. Das Original-PDF bleibt
    in import_quellen; pdftotext dient ausschließlich der Textextraktion.
    """
    import subprocess
    import tempfile
    year = int(re.search(r'Joker_(\d{4})',filename)[1])
    with tempfile.TemporaryDirectory(prefix='lotto-pdf-') as tmp:
        from pathlib import Path
        path = Path(tmp)/'source.pdf'; path.write_bytes(raw)
        result = subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,check=True)
    records,issues = [],[]
    for lineno,line in enumerate(result.stdout.decode().splitlines(),1):
        if not re.match(r'^\s*(?:So|Mi|Fr|Mo|Di|Do|Sa)\s+\d',line): continue
        try:
            parts=line.split(); d,m,*_=parts[1].split('.')
            number=''.join(parts[2:8]); rest=[p for p in parts[8:] if p!='à']
            if len(number)!=6 or not number.isascii() or not number.isdigit() or len(rest)!=7: raise ValueError('Unerwartete PDF-Spalten')
            qs=[quote('1',rest[0],rest[1],'EUR','6_rang_pdf')]
            qs.extend(quote(str(rank),count,'','EUR','6_rang_pdf') for rank,count in enumerate(rest[2:],2))
            records.append({'spiel':'joker','datum':dt.date(year,int(m),int(d)).isoformat(),'nummer':number,'quoten':qs,'zeile':lineno})
        except (ValueError,IndexError,ArithmeticError) as e: issues.append((lineno,f'L003: {e}',line))
    if not records: raise ValueError('L003: Keine Joker-Ziehungen erkannt')
    return records,issues


def parse_joker_csv(raw, filename):
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: text = raw.decode('cp1252')
    year = int(re.search(r'Joker_(\d{4})',filename)[1]); records,issues=[],[]
    for lineno,row in enumerate(csv.reader(text.splitlines(),delimiter=';'),1):
        if not row or not any(row) or row[0]=='Datum': continue
        try:
            match=re.fullmatch(r'\w+\s+(\d+)\.(\d+)\.',row[0].strip())
            if not match: raise ValueError('Unbekanntes Datum')
            digits=[Decimal(x.replace(',','.')) for x in row[1:7]]
            if len(digits)!=6 or any(d!=int(d) or d<0 or d>9 for d in digits): raise ValueError('Ungültige Jokerziffer')
            qs=[quote('1',row[7],row[9],'EUR','6_rang_pdf')]
            qs.extend(quote(str(rank),count,'','EUR','6_rang_pdf') for rank,count in enumerate(row[10:15],2))
            if len(qs)!=6: raise ValueError('Fehlende Gewinnklassen')
            records.append({'spiel':'joker','datum':dt.date(year,int(match[2]),int(match[1])).isoformat(),'nummer':''.join(str(int(d)) for d in digits),'quoten':qs,'zeile':lineno})
        except (ValueError,IndexError,ArithmeticError) as e: issues.append((lineno,f'L003: {e}',row))
    if not records: raise ValueError('L003: Keine Joker-Ziehungen erkannt')
    return records,issues
