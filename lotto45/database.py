"""Verlustfreies SQLite-Archiv mit getrennten Tippkatalogen und Ziehungen.

Tipps sind ungeordnete Mengen; Ziehungsreihenfolgen gehören zur Ziehung.
Geldbeträge werden als ganze Hundertstel der Originalwährung gespeichert.
Jeder Quellenstand bleibt als unveränderte Bytefolge erhalten. Änderungen
werden zusätzlich mit vorherigem/nachfolgendem Datensatz protokolliert.
"""
import datetime as dt
import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES('schema_version','1');
CREATE TABLE IF NOT EXISTS lotto_tipps(
 id INTEGER PRIMARY KEY, n1 INTEGER NOT NULL,n2 INTEGER NOT NULL,n3 INTEGER NOT NULL,
 n4 INTEGER NOT NULL,n5 INTEGER NOT NULL,n6 INTEGER NOT NULL,
 CHECK(1<=n1 AND n1<n2 AND n2<n3 AND n3<n4 AND n4<n5 AND n5<n6 AND n6<=45),
 UNIQUE(n1,n2,n3,n4,n5,n6));
CREATE TABLE IF NOT EXISTS joker_tipps(
 nummer TEXT PRIMARY KEY CHECK(length(nummer)=6 AND nummer NOT GLOB '*[^0-9]*')) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS import_quellen(
 id INTEGER PRIMARY KEY, uri TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
 original BLOB NOT NULL, importiert TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_fehler(
 id INTEGER PRIMARY KEY, quelle_id INTEGER NOT NULL REFERENCES import_quellen(id),
 zeile INTEGER, meldung TEXT NOT NULL, roh TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lotto_ziehungen(
 id INTEGER PRIMARY KEY, datum TEXT NOT NULL, kennung TEXT NOT NULL DEFAULT 'haupt',
 tipp_id INTEGER NOT NULL REFERENCES lotto_tipps(id), zusatzzahl INTEGER NOT NULL CHECK(zusatzzahl BETWEEN 1 AND 45),
 extras TEXT NOT NULL DEFAULT '{}', UNIQUE(datum,kennung));
CREATE INDEX IF NOT EXISTS lotto_tipp_ziehungen ON lotto_ziehungen(tipp_id);
CREATE TABLE IF NOT EXISTS lotto_ziehungszahlen(
 ziehung_id INTEGER NOT NULL REFERENCES lotto_ziehungen(id),
 position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 6), zahl INTEGER NOT NULL CHECK(zahl BETWEEN 1 AND 45),
 PRIMARY KEY(ziehung_id,position), UNIQUE(ziehung_id,zahl));
CREATE TABLE IF NOT EXISTS joker_ziehungen(
 id INTEGER PRIMARY KEY, datum TEXT NOT NULL, kennung TEXT NOT NULL DEFAULT 'haupt',
 nummer TEXT NOT NULL REFERENCES joker_tipps(nummer), extras TEXT NOT NULL DEFAULT '{}', UNIQUE(datum,kennung));
CREATE INDEX IF NOT EXISTS joker_tipp_ziehungen ON joker_ziehungen(nummer);
CREATE TABLE IF NOT EXISTS gewinnklassen(
 id INTEGER PRIMARY KEY, spiel TEXT NOT NULL CHECK(spiel IN ('lotto','joker')), regelwerk TEXT NOT NULL,
 code TEXT NOT NULL, gueltig_ab TEXT, gueltig_bis TEXT, UNIQUE(spiel,regelwerk,code));
CREATE TABLE IF NOT EXISTS lotto_quoten(
 ziehung_id INTEGER NOT NULL REFERENCES lotto_ziehungen(id), klasse_id INTEGER NOT NULL REFERENCES gewinnklassen(id),
 gewinner INTEGER CHECK(gewinner>=0), waehrung TEXT NOT NULL CHECK(waehrung IN ('ATS','EUR')),
 betrag_hundertstel INTEGER CHECK(betrag_hundertstel>=0),
 betrag_art TEXT NOT NULL CHECK(betrag_art IN ('je_gewinn','jackpot','unbekannt')),
 status TEXT NOT NULL, original TEXT NOT NULL, PRIMARY KEY(ziehung_id,klasse_id));
CREATE TABLE IF NOT EXISTS joker_quoten(
 ziehung_id INTEGER NOT NULL REFERENCES joker_ziehungen(id), klasse_id INTEGER NOT NULL REFERENCES gewinnklassen(id),
 gewinner INTEGER CHECK(gewinner>=0), waehrung TEXT NOT NULL CHECK(waehrung IN ('ATS','EUR')),
 betrag_hundertstel INTEGER CHECK(betrag_hundertstel>=0),
 betrag_art TEXT NOT NULL CHECK(betrag_art IN ('je_gewinn','jackpot','unbekannt')),
 status TEXT NOT NULL, original TEXT NOT NULL, PRIMARY KEY(ziehung_id,klasse_id));
CREATE TABLE IF NOT EXISTS lotto_quellen(
 ziehung_id INTEGER NOT NULL REFERENCES lotto_ziehungen(id), quelle_id INTEGER NOT NULL REFERENCES import_quellen(id),
 zeile INTEGER NOT NULL, PRIMARY KEY(ziehung_id,quelle_id,zeile));
CREATE TABLE IF NOT EXISTS joker_quellen(
 ziehung_id INTEGER NOT NULL REFERENCES joker_ziehungen(id), quelle_id INTEGER NOT NULL REFERENCES import_quellen(id),
 zeile INTEGER NOT NULL, PRIMARY KEY(ziehung_id,quelle_id,zeile));
CREATE TABLE IF NOT EXISTS aenderungen(
 id INTEGER PRIMARY KEY, spiel TEXT NOT NULL, ziehung_id INTEGER NOT NULL,
 quelle_id INTEGER NOT NULL REFERENCES import_quellen(id), zeit TEXT NOT NULL,
 vorher TEXT, nachher TEXT NOT NULL);
'''


def connect(path,*,create=True):
    """Importe dürfen Archive anlegen; Anzeigen öffnen bestehende Dateien nur lesend."""
    if not create:
        con=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
        con.row_factory=sqlite3.Row
        return con
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA journal_mode=WAL')
    con.executescript(SCHEMA)
    version = con.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
    if version != '1':
        con.close()
        raise ValueError('L001: Unbekannte Datenbankversion')
    from .schema import ensure
    ensure(con,path)
    return con


def tip_id(numbers):
    """Lexikografischer Rang: stabile IDs ohne Datenbanksuche oder große Cacheliste."""
    ns = tuple(sorted(numbers))
    if len(ns) != 6 or any(type(n) is not int for n in ns) or len(set(ns)) != 6 or not 1 <= ns[0] < ns[-1] <= 45:
        raise ValueError('L002: Sechs verschiedene ganze Zahlen von 1 bis 45 erforderlich')
    rank, prev = 1, 0
    for i, n in enumerate(ns):
        for skipped in range(prev+1, n):
            rank += math.comb(45-skipped, 5-i)
        prev = n
    return rank


def generate(con, progress=print):
    """Begrenzter Arbeitsspeicher; bestätigte Blöcke nach Abbruch fortsetzbar."""
    for game, total, iterator, sql in [
        ('lotto',math.comb(45,6), enumerate(itertools.combinations(range(1,46),6),1),
         'INSERT OR IGNORE INTO lotto_tipps VALUES(?,?,?,?,?,?,?)'),
        ('joker',1000000, ((f'{n:06d}',) for n in range(1000000)),
         'INSERT OR IGNORE INTO joker_tipps VALUES(?)')]:
        key = game+'_katalog_fertig'
        if con.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone():
            progress(f'{game}: {total:,}'); continue
        count = 0
        while batch := list(itertools.islice(iterator, 25000)):
            if game == 'lotto': batch = [(i,*ns) for i,ns in batch]
            with con: con.executemany(sql,batch)
            count += len(batch)
            if count % 500000 == 0 or count == total: progress(f'{game}: {count:,} / {total:,}')
        actual = con.execute(f'SELECT count(*) FROM {game}_tipps').fetchone()[0]
        if actual != total: raise ValueError('L001: Tippkatalog unvollständig')
        with con: con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,str(total)))
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')


def snapshot(con, game, draw_id):
    row = con.execute(f'SELECT * FROM {game}_ziehungen WHERE id=?',(draw_id,)).fetchone()
    if not row: return None
    result = dict(row)
    result['quoten'] = [dict(r) for r in con.execute(f'SELECT * FROM {game}_quoten WHERE ziehung_id=? ORDER BY klasse_id',(draw_id,))]
    if game == 'lotto': result['reihenfolge'] = [r[0] for r in con.execute('SELECT zahl FROM lotto_ziehungszahlen WHERE ziehung_id=? ORDER BY position',(draw_id,))]
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def _ingest(con, raw, uri, records, issues=(), allow_corrections=False, fill_missing_only=False):
    """Ein Quellenstand atomar. Konflikte standardmäßig erfassen statt überschreiben.

    JSON-Zusatzfelder bleiben in extras bzw. der unveränderten Quelle erhalten.
    Explizite Korrekturen ersetzen gelieferte Werte, nie fehlende Informationen.
    fill_missing_only ergänzt ausschließlich unbekannte Quotenfelder, wenn
    die übrigen bekannten Werte übereinstimmen. Vollständige Quoten bleiben.
    """
    digest = hashlib.sha256(raw).hexdigest()
    existing = con.execute('SELECT id FROM import_quellen WHERE sha256=?',(digest,)).fetchone()
    if existing: return {'bereits_importiert': True, 'quelle': existing[0]}
    accepted = changes = conflicts = new_count = updated_count = identical_count = 0
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with con:
        source = con.execute('INSERT INTO import_quellen(uri,sha256,original,importiert) VALUES(?,?,?,?)',(uri,digest,raw,now)).lastrowid
        for line, message, original in issues:
            con.execute('INSERT INTO import_fehler(quelle_id,zeile,meldung,roh) VALUES(?,?,?,?)',(source,line,message,json.dumps(original,ensure_ascii=False)))
        for r in records:
            game = r['spiel']
            if game not in ('lotto','joker'): raise ValueError('L002: Unbekanntes Spiel')
            date = dt.date.fromisoformat(r['datum']).isoformat()
            identity = str(r.get('kennung','haupt'))
            if not identity: raise ValueError('L002: Leere Ziehungskennung')
            if game == 'lotto':
                ns = sorted(r['zahlen']); tid = tip_id(ns); bonus = r['zusatzzahl']
                if type(bonus) is not int or bonus not in range(1,46) or bonus in ns: raise ValueError('L002: Ungültige Zusatzzahl')
                order = r.get('reihenfolge')
                if order is not None and (len(order)!=6 or sorted(order)!=ns): raise ValueError('L002: Ziehungsreihenfolge stimmt nicht überein')
                con.execute('INSERT OR IGNORE INTO lotto_tipps VALUES(?,?,?,?,?,?,?)',(tid,*ns))
                fields = {'tipp_id':tid,'zusatzzahl':bonus}
            else:
                number = r['nummer']
                if not isinstance(number,str) or len(number)!=6 or any(c not in '0123456789' for c in number): raise ValueError('L002: Joker muss eine sechsstellige Zeichenfolge sein')
                con.execute('INSERT OR IGNORE INTO joker_tipps VALUES(?)',(number,))
                fields = {'nummer':number}
            old = con.execute(f'SELECT * FROM {game}_ziehungen WHERE datum=? AND kennung=?',(date,identity)).fetchone()
            if old and any(old[k]!=v for k,v in fields.items()) and not allow_corrections:
                con.execute('INSERT INTO import_fehler(quelle_id,zeile,meldung,roh) VALUES(?,?,?,?)',(source,r.get('zeile',0),'L003: Abweichende Ziehung; manuelle Prüfung erforderlich',json.dumps(r,ensure_ascii=False)))
                conflicts += 1; continue
            extras = json.loads(old['extras']) if old else {}
            extras.update({k:v for k,v in r.items() if k not in {'spiel','datum','kennung','zahlen','zusatzzahl','nummer','reihenfolge','quoten','zeile'}})
            if old:
                draw_id = old['id']; before = snapshot(con,game,draw_id)
                con.execute(f"UPDATE {game}_ziehungen SET {','.join(k+'=?' for k in fields)},extras=? WHERE id=?",(*fields.values(),json.dumps(extras,ensure_ascii=False),draw_id))
            else:
                before = None
                draw_id = con.execute(f"INSERT INTO {game}_ziehungen(datum,kennung,{','.join(fields)},extras) VALUES({','.join('?' for _ in range(len(fields)+3))})",(date,identity,*fields.values(),json.dumps(extras,ensure_ascii=False))).lastrowid
            if game == 'lotto':
                current = [x[0] for x in con.execute('SELECT zahl FROM lotto_ziehungszahlen WHERE ziehung_id=? ORDER BY position',(draw_id,))]
                # Bei geänderten Zahlen darf eine alte Reihenfolge nicht fortbestehen.
                if current and sorted(current)!=ns:
                    con.execute('DELETE FROM lotto_ziehungszahlen WHERE ziehung_id=?',(draw_id,)); current=[]
                if order is not None:
                    if current and current != order and not allow_corrections:
                        conflicts += 1
                        con.execute('INSERT INTO import_fehler(quelle_id,zeile,meldung,roh) VALUES(?,?,?,?)',(source,r.get('zeile',0),'L003: Abweichende Reihenfolge',json.dumps(r,ensure_ascii=False)))
                    else:
                        con.execute('DELETE FROM lotto_ziehungszahlen WHERE ziehung_id=?',(draw_id,))
                        con.executemany('INSERT INTO lotto_ziehungszahlen VALUES(?,?,?)',((draw_id,i,n) for i,n in enumerate(order,1)))
            for q in r.get('quoten',[]):
                rule = q.get('regelwerk','unbekannt')
                con.execute('INSERT OR IGNORE INTO gewinnklassen(spiel,regelwerk,code) VALUES(?,?,?)',(game,rule,q['klasse']))
                klass = con.execute('SELECT id FROM gewinnklassen WHERE spiel=? AND regelwerk=? AND code=?',(game,rule,q['klasse'])).fetchone()[0]
                for k in ('gewinner','betrag_hundertstel'):
                    if q.get(k) is not None and (type(q[k]) is not int or q[k]<0): raise ValueError('L002: Ungültiger Ganzzahlbetrag oder Gewinneranzahl')
                values = (q.get('gewinner'),q['waehrung'],q.get('betrag_hundertstel'),q.get('betrag_art','unbekannt'),q.get('status',''),json.dumps(q,ensure_ascii=False,sort_keys=True))
                oldq = con.execute(f'SELECT * FROM {game}_quoten WHERE ziehung_id=? AND klasse_id=?',(draw_id,klass)).fetchone()
                # Jahresdateien ohne Beträge dürfen separat belegte Ergänzungen
                # beim nächsten Download weder löschen noch als Konflikt melden.
                if oldq and oldq['waehrung']==q['waehrung']:
                    values=(values[0] if values[0] is not None else oldq['gewinner'],values[1],
                            values[2] if values[2] is not None else oldq['betrag_hundertstel'],*values[3:])
                supplement=False
                if oldq and fill_missing_only:
                    fields_to_fill=('gewinner','betrag_hundertstel')
                    if not any(oldq[k] is None and q.get(k) is not None for k in fields_to_fill):continue
                    if oldq['waehrung']==q['waehrung'] and all(oldq[k] is None or q.get(k) is None or oldq[k]==q[k] for k in fields_to_fill):
                        values=(oldq['gewinner'] if oldq['gewinner'] is not None else q.get('gewinner'),
                                oldq['waehrung'],oldq['betrag_hundertstel'] if oldq['betrag_hundertstel'] is not None else q.get('betrag_hundertstel'),
                                oldq['betrag_art'],oldq['status'],values[-1])
                        supplement=True
                if oldq and tuple(oldq)[2:7] != values[:5] and not (allow_corrections or supplement):
                    conflicts += 1
                    con.execute('INSERT INTO import_fehler(quelle_id,zeile,meldung,roh) VALUES(?,?,?,?)',(source,r.get('zeile',0),'L003: Abweichende Quote',json.dumps(q,ensure_ascii=False)))
                    continue
                if not oldq or tuple(oldq)[2:7] != values[:5]:
                    con.execute(f'INSERT OR REPLACE INTO {game}_quoten VALUES(?,?,?,?,?,?,?,?)',(draw_id,klass,*values))
            con.execute(f'INSERT OR IGNORE INTO {game}_quellen VALUES(?,?,?)',(draw_id,source,r.get('zeile',0)))
            after = snapshot(con,game,draw_id)
            if before != after:
                con.execute('INSERT INTO aenderungen(spiel,ziehung_id,quelle_id,zeit,vorher,nachher) VALUES(?,?,?,?,?,?)',(game,draw_id,source,now,before,after)); changes += 1
                if before is None:new_count+=1
                else:updated_count+=1
            else:identical_count+=1
            accepted += 1
    return {'quelle':source,'ziehungen':accepted,'aenderungen':changes,'konflikte':conflicts,'parser_hinweise':len(issues),'neu':new_count,'aktualisiert':updated_count,'identisch':identical_count}


def ingest(con,raw,uri,records,issues=(),allow_corrections=False,fill_missing_only=False):
    """Atomaren Import einschließlich Fehlern und Duplikaten dauerhaft protokollieren."""
    tracked=con.execute("SELECT 1 FROM sqlite_master WHERE name='import_run'").fetchone()
    records=list(records);issues=list(issues)
    digest=hashlib.sha256(raw).hexdigest();started=dt.datetime.now(dt.timezone.utc).isoformat()
    try:result=_ingest(con,raw,uri,records,issues,allow_corrections,fill_missing_only)
    except Exception as error:
        if tracked:
            with con:con.execute('INSERT INTO import_run(started,url,sha256,status,rejected,details) VALUES(?,?,?,?,?,?)',
                                 (started,uri,digest,'error',len(records),str(error)))
        raise
    if tracked:
        status='unchanged' if result.get('bereits_importiert') else 'review' if result.get('konflikte') or issues else 'success'
        with con:con.execute('INSERT INTO import_run(started,url,sha256,status,read_count,changed,rejected,details) VALUES(?,?,?,?,?,?,?,?)',
                             (started,uri,digest,status,len(records),result.get('aenderungen',0),result.get('konflikte',0)+len(issues),json.dumps(result)))
    return result


def summary(con):
    result = {}
    for game in ('lotto','joker'):
        result[game] = dict(con.execute(f'SELECT count(*) anzahl,min(datum) von,max(datum) bis FROM {game}_ziehungen').fetchone())
        result[game]['tipps'] = con.execute(f'SELECT count(*) FROM {game}_tipps').fetchone()[0]
        result[game]['quoten'] = con.execute(f'SELECT count(*) FROM {game}_quoten').fetchone()[0]
    result['import_hinweise'] = con.execute('SELECT count(*) FROM import_fehler').fetchone()[0]
    return result


def has_other_draw_kinds(path,game):
    """Kennungsfilter nur anbieten, wenn das Spielarchiv weitere Kennungen enthält."""
    from contextlib import closing
    if game not in ('lotto','joker'):raise ValueError('L002: Unbekanntes Spiel')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        return con.execute(f"SELECT 1 FROM {game}_ziehungen WHERE kennung <> 'haupt' LIMIT 1").fetchone() is not None
