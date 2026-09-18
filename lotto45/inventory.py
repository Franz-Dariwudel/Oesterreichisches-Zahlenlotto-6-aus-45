"""Lesender Datenbestandsbericht mit tatsächlichen Zeilenzahlen und Dateigrößen.

Die Oberfläche trennt Tippkataloge, importierte Ziehungen und Quelldaten.
Eine SQLite-Lesetransaktion hält alle Tabellenzahlen auf demselben Stand.
Dateigrößen werden anschließend vom Dateisystem gelesen; sie können sich
bei gleichzeitig laufenden Importen ändern.
"""
from contextlib import closing
from pathlib import Path
import math
import sqlite3


def read_inventory(path):
    path=Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=60)) as con:
        con.row_factory=sqlite3.Row
        con.execute('BEGIN')
        tables={}
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            name=row['name'];identifier='"'+name.replace('"','""')+'"'
            tables[name]=con.execute(f'SELECT count(*) FROM {identifier}').fetchone()[0]
        games={}
        for game,possible in (('lotto',math.comb(45,6)),('joker',1000000)):
            dates=con.execute(f'SELECT min(datum) first,max(datum) last FROM {game}_ziehungen').fetchone()
            games[game]={
                'tips':tables[game+'_tipps'],'possible':possible,
                'draws':tables[game+'_ziehungen'],'quotes':tables[game+'_quoten'],
                'first':dates['first'],'last':dates['last'],
                'missing_amounts':con.execute(f'SELECT count(*) FROM {game}_quoten WHERE betrag_hundertstel IS NULL').fetchone()[0],
            }
    sizes={'database':path.stat().st_size}
    for suffix in ('wal','shm'):
        try:sizes[suffix]=Path(str(path)+'-'+suffix).stat().st_size
        except FileNotFoundError:sizes[suffix]=0
    return {'path':str(path),'tables':tables,'games':games,'sizes':sizes,
            'total_rows':sum(tables.values()),'total_draws':sum(game['draws'] for game in games.values())}
