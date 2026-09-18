"""Gespeicherte Importhinweise erklären, ohne Originalmeldungen zu verändern.

Kategorien bestimmen nur die Darstellung. Unbekannte Meldungen bleiben als
ungeklärte Hinweise sichtbar; sie werden nicht als harmlose Texte eingestuft.
"""
import json


def category(message, raw):
    """Bekannte Importfälle auf sprachunabhängige Erklärungsschlüssel abbilden."""
    text=message.removeprefix('L003: ').strip()
    if text.startswith('Abweichende Quote'):return 'quote_conflict'
    if text.startswith('Abweichende Ziehung'):return 'draw_conflict'
    if text.startswith('Mehrdeutiges doppeltes Joker-Datum'):return 'duplicate'
    if text.startswith('Originalreihenfolge oder ZZ weicht ab'):return 'invalid_order'
    if text.startswith('Abweichende Reihenfolge'):return 'order_conflict'
    if text.startswith('Quote nicht lesbar'):return 'invalid_quote'
    try:original=json.loads(raw)
    except (ValueError,TypeError):original=None
    # Nur bekannte Textzeilen als Erläuterung werten, nicht beliebige Rohdaten.
    if isinstance(original,list) and all(isinstance(value,str) for value in original):
        content=' '.join(original).casefold()
        if 'ziehung wurde auf' in content and 'verschoben' in content:return 'postponed'
        if len(original)>2 and ''.join(original[2].split()).casefold()=='entfallen':return 'cancelled'
        if text=='Nicht zugeordnete Archivzeile' and 'einführung von 2 lottoziehungen' in content:return 'archive_note'
    return 'unknown'


def read_reviews(con):
    """Hinweise samt Quellen und zuordenbaren Daten lesen; keine BLOB-Archive laden."""
    rows=[dict(row) for row in con.execute('''SELECT f.*,s.uri FROM import_fehler f
        JOIN import_quellen s ON s.id=f.quelle_id ORDER BY f.id''')]
    dates={}
    for game in ('lotto','joker'):
        for row in con.execute(f'''SELECT s.quelle_id,s.zeile,d.datum FROM {game}_quellen s
                JOIN {game}_ziehungen d ON d.id=s.ziehung_id'''):
            dates.setdefault((row[0],row[1]),set()).add(row[2])
    for row in rows:
        row['category']=category(row['meldung'],row['roh'])
        row['dates']=sorted(dates.get((row['quelle_id'],row['zeile']),()))
        try:original=json.loads(row['roh'])
        except (ValueError,TypeError):original=None
        if isinstance(original,dict) and isinstance(original.get('datum'),str):
            row['dates']=[original['datum']]
    return rows
