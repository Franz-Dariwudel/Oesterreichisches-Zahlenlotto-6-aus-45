#!/usr/bin/python3
"""DEB aus bereinigtem Build; private Arbeitsdaten bleiben ausgeschlossen."""
import shutil,subprocess,tarfile,tempfile
from pathlib import Path
from lotto45 import VERSION
root=Path(__file__).resolve().parent
out=root/'auslieferung';out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    stage=Path(temp)/'package'; app=stage/'usr/lib/6aus45';app.mkdir(parents=True)
    archive=root/'work/build'/f'6aus45-{VERSION}-python312-linux.tar.gz'
    with tarfile.open(archive) as tar:tar.extractall(Path(temp)/'compiled',filter='data')
    compiled=next((Path(temp)/'compiled').iterdir())
    for folder in ('lotto45','resources','languages','help','vendor'):shutil.copytree(compiled/folder,app/folder)
    for file in ('launch.py','desktop_setup.py','seed_database.py','launcher.desktop'):shutil.copy2(root/'packaging'/file,app/file)
    shutil.copy2(root/'work/publication/lotto-datenbank.zip',app/'lotto-datenbank.zip')
    def write(name,text,mode=0o644):
        p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(mode)
    write('usr/bin/6aus45','#!/bin/sh\nexec /usr/bin/python3 -B "$(dirname "$(readlink -f "$0")")/../lib/6aus45/launch.py" "$@"\n',0o755)
    write('usr/share/applications/oesterreichisches-zahlenlotto.desktop',(app/'launcher.desktop').read_text())
    icon=stage/'usr/share/pixmaps/6aus45.png';icon.parent.mkdir(parents=True);shutil.copy2(root/'resources/icon.png',icon)
    write('etc/xdg/autostart/oesterreichisches-zahlenlotto-desktop.desktop','[Desktop Entry]\nType=Application\nName=Zahlenlotto Desktop-Starter\nExec=/usr/bin/python3 -B /usr/lib/6aus45/desktop_setup.py --user\nNoDisplay=true\n')
    write('usr/share/doc/oesterreichisches-zahlenlotto/copyright',(root/'LICENSE').read_text())
    write('DEBIAN/control',f'Package: oesterreichisches-zahlenlotto\nVersion: {VERSION}\nArchitecture: amd64\nMaintainer: Josef Lehner <office@dogtruck.eu>\nDepends: python3 (>= 3.12), python3 (<< 3.13), python3-gi, python3-cairo, gir1.2-gtk-4.0, poppler-utils, xdg-user-dirs, libglib2.0-bin\nSection: education\nPriority: optional\nDescription: Oesterreichisches Zahlenlotto 6 aus 45 und Joker\n GTK-4-Archiv mit zehn Sprachen und Hilfe.\n')
    for name,action in [('postinst','configure'),('prerm','remove')]:
        option=' --remove' if name=='prerm' else ''
        write('DEBIAN/'+name,f'#!/bin/sh\nset -e\nif [ "$1" = "{action}" ]; then\n if [ -n "${{DPKG_ROOT:-}}" ]; then\n  /usr/bin/python3 -B "$DPKG_ROOT/usr/lib/6aus45/desktop_setup.py"{option} --user\n else\n  /usr/bin/python3 -B /usr/lib/6aus45/desktop_setup.py --system{option}\n fi\nfi\n',0o755)
    target=out/f'oesterreichisches-zahlenlotto_{VERSION}_amd64.deb'
    subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(target)],check=True)
    print(target)
