"""DEB-Metadaten prüfen: Dateien müssen nach root-Installation lesbar sein.

Die Prüfung liest das tatsächliche Datenarchiv des Pakets und funktioniert
auch ohne root. Ein bloßer Starttest als Ersteller erkennt 0600-Dateien nicht.
"""
import subprocess,sys,tarfile
from pathlib import Path

def check(package):
    failures=[];count=0
    process=subprocess.Popen(['dpkg-deb','--fsys-tarfile',str(package)],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
        for member in archive:
            if member.name in ('.','./'):continue
            count+=1
            if member.uid!=0 or member.gid!=0:failures.append(f'{member.name}: Eigentümer ist nicht root:root')
            if member.isdir() and member.mode & 0o005 != 0o005:failures.append(f'{member.name}: Verzeichnis nicht allgemein durchsuchbar ({member.mode:o})')
            elif member.isfile() and not member.mode & 0o004:failures.append(f'{member.name}: Datei nicht allgemein lesbar ({member.mode:o})')
            if member.mode & 0o022:failures.append(f'{member.name}: für Gruppe/andere schreibbar ({member.mode:o})')
    assert process.wait()==0,'DEB-Datenarchiv nicht lesbar'
    if failures:raise AssertionError('\n'.join(failures))
    print(f'{count} Paketpfade: root:root, für normale Benutzer lesbar, sichere Schreibrechte.')

if __name__=='__main__':check(Path(sys.argv[1]))
