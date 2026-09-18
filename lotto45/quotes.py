"""Gewinnquoten lesend nach Spiel und Datum abfragen, GPL-3.0-only.

Nur Ziehungen mit gespeicherten Quoten erscheinen. NULL bleibt unbekannt, 0 bleibt
ein gültiger Wert; Originalwährungen und verschiedene Ziehungen am Tag bleiben
getrennt. Die Oberfläche ergänzt gegebenenfalls bestätigte Joker-Standardbeträge.
"""
import re


def jackpot_label(status):
    """Nur die Anzeige vereinheitlichen; historische Originalkürzel bleiben erhalten."""
    text=status.strip().upper()
    if text in ('JP','JACKPOT','JACKPOT-POOL','JACKPOT POOL'):return 'JP'
    if text in ('DJP','DOPPELJACKPOT'):return '2JP'
    match=re.fullmatch(r'(\d+)[\s-]*JP',text)
    if match:return match[1]+'JP'
    return status.strip() or 'JP'


def search_quotes(con,game,query):
    if game not in ('lotto','joker'):raise ValueError('L002: Unbekanntes Spiel')
    cursor=con.execute(f'''SELECT d.id,d.datum,d.kennung,k.code,q.klasse_id,
        q.gewinner,q.waehrung,q.betrag_hundertstel,q.betrag_art,q.status
        FROM {game}_ziehungen d JOIN {game}_quoten q ON q.ziehung_id=d.id
        LEFT JOIN gewinnklassen k ON k.id=q.klasse_id
        WHERE d.datum BETWEEN ? AND ? ORDER BY d.datum DESC,d.kennung DESC,d.id DESC,k.id''',
        (query.period.start,query.period.end))
    columns=[column[0] for column in cursor.description]
    return [dict(zip(columns,row)) for row in cursor if query.matches(row[1])]


def group_months(rows):
    """Alle Quoten chronologisch nach Jahr/Monat gruppieren; Zeilen unverändert lassen."""
    months={}
    for row in rows:months.setdefault(row['datum'][:7],[]).append(row)
    return {month:months[month] for month in sorted(months,reverse=True)}
