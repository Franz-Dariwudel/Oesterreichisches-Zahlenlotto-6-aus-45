#!/usr/bin/python3
"""Schreibbare Benutzerausgabe aktualisieren; Daten und Einstellungen erhalten."""
import hashlib, json, os, shutil, sys
from pathlib import Path
from seed_database import install_database
from installation import prepare_state
base=Path(__file__).resolve().parent
root=Path.home()/'.local/share/oesterreichisches-zahlenlotto'
prepare_state(root)
install_database(base,root)
journal=root/'installation.json'
data=json.loads(journal.read_text()) if journal.exists() else {'files':[]}
data.setdefault('hashes',{})
for folder in ('lotto45','resources','languages','help'):
    for source in (base/folder).rglob('*'):
        if not source.is_file() or '__pycache__' in source.parts:continue
        target=root/source.relative_to(base)
        target.parent.mkdir(parents=True,exist_ok=True)
        # Heruntergeladene zusätzliche Sprachen und persönliche Daten erhalten.
        old=data['hashes'].get(str(target))
        if folder in ('languages','help') and target.exists() and (old is None or hashlib.sha256(target.read_bytes()).hexdigest()!=old):continue
        shutil.copy2(source,target)
        data['hashes'][str(target)]=hashlib.sha256(target.read_bytes()).hexdigest()
        if str(target) not in data['files']:data['files'].append(str(target))
for folder in ('config','logs','data'):(root/folder).mkdir(exist_ok=True)
for folder in ('vendor',):
    target=root/folder
    if not target.exists():target.symlink_to(base/folder,target_is_directory=True)
    if str(target) not in data['files']:data['files'].append(str(target))
for name,text in [('config/settings.json',json.dumps({'language':'de','repository':'Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45','max_tips':10000})),('config/download_sources.json',(base/'resources/default_sources.json').read_text()),('logs/error.log','')]:
    target=root/name
    if not target.exists():
        target.write_text(text);data['files'].append(str(target))
journal.write_text(json.dumps(data,indent=2))
os.chdir(root)
os.execv('/usr/bin/python3',['/usr/bin/python3','-B','-m','lotto45',*sys.argv[1:]])
