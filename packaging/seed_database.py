"""Mitgelieferte Datenbank geprüft und ohne Überschreiben installieren."""
import hashlib,json,os,tempfile,zipfile
from pathlib import Path

def install_database(base, root):
    folder=root/'data';folder.mkdir(parents=True,exist_ok=True)
    target=folder/'lotto.sqlite3'
    if target.exists():return
    temporary=None
    try:
        with zipfile.ZipFile(base/'lotto-datenbank.zip') as archive:
            manifest=json.loads(archive.read('datenbank-info.json'))
            digest=hashlib.sha256()
            with archive.open('lotto.sqlite3') as source, tempfile.NamedTemporaryFile(dir=folder,prefix='.database-',delete=False) as out:
                temporary=Path(out.name)
                while chunk:=source.read(1024*1024):out.write(chunk);digest.update(chunk)
                out.flush();os.fsync(out.fileno())
            if digest.hexdigest()!=manifest['sha256']:raise ValueError('L006: Datenbank-Prüfsumme ungültig')
            # Hardlink ist atomar und scheitert, falls inzwischen eine DB angelegt wurde.
            try:os.link(temporary,target)
            except FileExistsError:return
            journal=root/'installation.json'
            data=json.loads(journal.read_text()) if journal.exists() else {'files':[]}
            data['seed_database']={'path':str(target),'sha256':digest.hexdigest()}
            journal.write_text(json.dumps(data,indent=2))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
