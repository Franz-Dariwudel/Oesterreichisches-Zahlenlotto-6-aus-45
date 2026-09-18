#!/usr/bin/env python3
"""Benutzerinstallation mit Dateijournal. GPL-3.0-only, Josef Lehner.

Nur neu angelegte Programmdateien erfassen. Vorhandene Ziele niemals
überschreiben. Bei Deinstallation geänderte Dateien und spätere Datenbanken
als Benutzerdaten erhalten und melden. Keine Administratorrechte nötig.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,sqlite3
from contextlib import closing
from pathlib import Path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--prefix',type=Path,default=Path.home()/'.local/share/6aus45')
 p.add_argument('--desktop-dir',type=Path)
 p.add_argument('--menu-dir',type=Path,default=Path.home()/'.local/share/applications')
 p.add_argument('--uninstall',action='store_true');args=p.parse_args()
 root=args.prefix.expanduser().resolve();journal=root/'installation.json'
 if args.uninstall:
  entries=json.loads(journal.read_text());remaining=[]
  # Bestätigte WAL-Daten zuerst zusammenführen, sonst könnte eine geänderte
  # Benutzer-DB fälschlich noch den Hash der leeren Installationsdatei tragen.
  for process in Path('/proc').iterdir():
   if not process.name.isdigit():continue
   try:
    active=(process/'cwd').resolve()==root and b'-m\x00lotto45' in (process/'cmdline').read_bytes()
   except (OSError,RuntimeError):continue
   if active:raise RuntimeError('Programm vor der Deinstallation schließen.')
  for name in entries['files']:
   database=Path(name)
   if database.suffix=='.sqlite3' and database.exists():
    with closing(sqlite3.connect(database,timeout=2)) as con:
     if con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:raise RuntimeError('Datenbank wird noch verwendet; Programm schließen.')
  for name,sha in entries['files'].items():
   target=Path(name)
   if not target.exists():continue
   if digest(target)!=sha and name not in entries.get('mutable',[]):remaining.append(name);continue
   target.unlink()
  journal.unlink()
  for name in sorted(entries['dirs'],key=len,reverse=True):
   try:Path(name).rmdir()
   except OSError:pass
  if root.exists():remaining.extend(str(p) for p in root.rglob('*') if p.is_file())
  print('Programmdateien deinstalliert. Erhaltene Benutzerdateien:',sorted(set(remaining)))
  return
 if root.exists():raise FileExistsError(f'Ziel bereits vorhanden: {root}; vorhandene Installation zuerst deinstallieren.')
 source=Path(__file__).resolve().parent
 desktop=args.desktop_dir
 if desktop is None:
  try:desktop=Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
  except (OSError,subprocess.SubprocessError):desktop=Path.home()/'Desktop'
 destinations=[desktop/'6aus45.desktop',args.menu_dir/'6aus45.desktop']
 for path in destinations:
  if path.exists():raise FileExistsError(f'Starter bereits vorhanden: {path}')
 created=[];dirs=[]
 def mkdir(path):
  missing=[];current=path
  while not current.exists():missing.append(current);current=current.parent
  path.mkdir(parents=True,exist_ok=True);dirs.extend(str(x) for x in reversed(missing))
 try:
  mkdir(root)
  for folder in ['lotto45','languages','help','resources']+(['vendor'] if (source/'vendor').is_dir() else []):
   for src in (source/folder).rglob('*'):
    if not src.is_file() or '__pycache__' in src.parts:continue
    dst=root/src.relative_to(source);mkdir(dst.parent);shutil.copy2(src,dst);created.append(dst)
  for folder in ['config','logs','data']:mkdir(root/folder)
  defaults={'config/settings.json':json.dumps({'language':'de','repository':'','max_tips':10000}),
            'config/download_sources.json':(source/'resources/default_sources.json').read_text(encoding='utf-8'), 'logs/error.log':''}
  for name,text in defaults.items():
   target=root/name;target.write_text(text);created.append(target)
  from lotto45.database import connect
  with closing(connect(root/'data/lotto.sqlite3')):pass
  created.append(root/'data/lotto.sqlite3')
  for name in ['LICENSE','README.md','CHANGELOG.md','DATABASE.md','DATA_STATUS.md','STATISTICS.md','CONCEPT_IMPLEMENTATION.md','THIRD_PARTY.md','requirements.txt','install.py']:
   shutil.copy2(source/name,root/name);created.append(root/name)
  entry=f'[Desktop Entry]\nType=Application\nName=6 aus 45\nComment=Lotto- und Joker-Archiv\nExec=/usr/bin/python3 -B -m lotto45\nPath={root}\nIcon={root}/resources/icon.png\nTerminal=false\nCategories=Education;\n'
  for path in destinations:
   mkdir(path.parent);path.write_text(entry);path.chmod(0o755);created.append(path)
   subprocess.run(['gio','set',str(path),'metadata::trusted','true'],capture_output=True)
  journal.write_text(json.dumps({'files':{str(f):digest(f) for f in created},'dirs':sorted(set(dirs)),
                                 'mutable':[str(root/name) for name in ('config/settings.json','config/download_sources.json','logs/error.log')]},indent=2))
 except Exception:
  for path in reversed(created):path.unlink(missing_ok=True)
  for name in sorted(set(dirs),key=len,reverse=True):
   try:Path(name).rmdir()
   except OSError:pass
  raise
 print(f'Installiert: {root}\nDesktop: {destinations[0]}\nDeinstallation: python3 {root}/install.py --prefix {root} --uninstall')

if __name__=='__main__':
 try:main()
 except Exception as e:print(f'L006: Installation/Deinstallation fehlgeschlagen: {e}',file=sys.stderr);sys.exit(1)
