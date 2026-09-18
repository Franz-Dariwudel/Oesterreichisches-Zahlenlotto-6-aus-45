"""Konsistente, bereinigte Downloadkopie; verändert die Arbeitsdatenbank nicht."""
from pathlib import Path
import sqlite3,json,zipfile,hashlib
root=Path(__file__).resolve().parents[1];folder=root/'work/publication'
target=folder/'lotto.sqlite3'
source=sqlite3.connect((root/'data/lotto_00.sqlite3').as_uri()+'?mode=ro',uri=True)
copy=sqlite3.connect(target);source.backup(copy);source.close()
copy.execute('PRAGMA foreign_keys=ON')
with copy:
 for table in ['batch_tip','tip_batch','stat_profile','import_run','source_cache','import_fehler']:
  copy.execute('DELETE FROM '+table)
 copy.execute("DELETE FROM metadata WHERE key NOT IN ('schema_version','extension_version','lotto_katalog_fertig','joker_katalog_fertig')")
 copy.execute('DELETE FROM data_source')
 for item in json.loads((root/'resources/default_sources.json').read_text()):
  copy.execute('INSERT INTO data_source(url,name,game,format,priority,enabled) VALUES(?,?,?,?,?,?)',(item['url'],item['name'],item['game'],item['format'],item['priority'],int(item['enabled'])))
 for ident,uri,sha in copy.execute('SELECT id,uri,sha256 FROM import_quellen').fetchall():
  if not uri.startswith(('https://','http://')):copy.execute('UPDATE import_quellen SET uri=? WHERE id=?',('archive:sha256:'+sha,ident))
copy.execute('PRAGMA journal_mode=DELETE');copy.execute('VACUUM')
assert list(copy.execute('PRAGMA integrity_check'))==[('ok',)]
assert not list(copy.execute('PRAGMA foreign_key_check'))
manifest={'date':'2026-09-18','database':'lotto.sqlite3','tables':{}}
for table in ['lotto_ziehungen','joker_ziehungen','lotto_tipps','joker_tipps','lotto_quoten','joker_quoten']:
 manifest['tables'][table]=copy.execute('SELECT count(*) FROM '+table).fetchone()[0]
for table in ['stat_profile','tip_batch','batch_tip','import_run','source_cache','import_fehler']:assert copy.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
copy.close()
manifest['sha256']=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
(folder/'datenbank-info.json').write_text(json.dumps(manifest,indent=2)+'\n')
with zipfile.ZipFile(folder/'lotto-datenbank.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 z.write(target,'lotto.sqlite3');z.write(folder/'datenbank-info.json','datenbank-info.json')
 z.writestr('LESEN.txt','Lotto-/Joker-Archiv, Stand 18.09.2026. Enthält historische Ziehungen, Quoten und vollständige Kombinationskataloge. Keine persönlichen Tippserien, Profile oder Sitzungsprotokolle.\nEntpacken, dann im Programm Gemeinsam > Datenbank auswählen. Die vorhandene Arbeitsdatenbank nicht überschreiben.\nQuellennachweise liegen in der Datenbank. Das Archiv ist keine Gewinnprognose.\n')
print(json.dumps(manifest,indent=2));print('ZIP bytes:',(folder/'lotto-datenbank.zip').stat().st_size)
