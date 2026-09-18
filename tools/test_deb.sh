#!/bin/bash
set -euo pipefail
project=$(cd "$(dirname "$0")/.." && pwd)
stage=$(mktemp -d "$project/work/deb-test-XXXXXX")
version=$(PYTHONPATH="$project" /usr/bin/python3 -B -c "from lotto45 import VERSION; print(VERSION)")
test_home="$stage/home"
run_in_test_home() { env HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" "$@"; }
package="$project/auslieferung/oesterreichisches-zahlenlotto_${version}-3_amd64.deb"
python3 -B "$project/tools/check_deb_permissions.py" "$package"
unset SUDO_UID PKEXEC_UID
mkdir -p "$test_home/.config" "$test_home/Schreibtisch" "$stage/root/var/lib/dpkg"
printf 'XDG_DESKTOP_DIR="$HOME/Schreibtisch"\n' > "$test_home/.config/user-dirs.dirs"
touch "$stage/root/var/lib/dpkg/status"
run_in_test_home dpkg --log="$stage/dpkg.log" --root="$stage/root" --force-not-root --force-script-chrootless --force-depends -i "$package"
dpkg-query --admindir="$stage/root/var/lib/dpkg" -W -f='${Status}\n' oesterreichisches-zahlenlotto
test -x "$test_home/Schreibtisch/oesterreichisches-zahlenlotto.desktop"
desktop-file-validate "$test_home/Schreibtisch/oesterreichisches-zahlenlotto.desktop"
icon=$(sed -n 's/^Icon=//p' "$test_home/Schreibtisch/oesterreichisches-zahlenlotto.desktop")
test -s "$icon"
python3 - "$test_home/.local/share/oesterreichisches-zahlenlotto/data/lotto.sqlite3" <<'CHECK'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
    counts=[db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('lotto_ziehungen','joker_ziehungen')]
    assert counts==[3683,3574],counts
    print('Installierte Datenbank: Lotto',counts[0],'Joker',counts[1])
CHECK
cmp "$icon" "$project/resources/icon.png"
run_in_test_home "$stage/root/usr/bin/6aus45" --version
mkdir -p "$stage/probe"
cp "$project/tools/deb_gui_probe.py" "$stage/probe/sitecustomize.py"
GSK_RENDERER=cairo PYTHONPATH="$stage/probe" LOTTO_DEB_GUI_PROBE="$stage/window.json" LOTTO_EXPECTED_VERSION="$version" \
    run_in_test_home gio launch "$test_home/Schreibtisch/oesterreichisches-zahlenlotto.desktop" > "$stage/gui.log" 2>&1
python3 - "$stage/window.json" <<'WINDOW'
import json,sys,time
from pathlib import Path
p=Path(sys.argv[1]);deadline=time.monotonic()+45
while not p.exists() and time.monotonic()<deadline:time.sleep(.2)
assert p.exists(),'Desktop-Start hat kein sichtbares Programmfenster geöffnet'
info=json.loads(p.read_text());assert info['mapped']
assert '/.local/share/oesterreichisches-zahlenlotto/lotto45/' in info['module'],info
print('Desktop-Start: sichtbares Fenster',info)
WINDOW
sleep 1
cat "$stage/gui.log"
cp "$stage/window.json" "$project/work/verification/deb-window-$version.json"
cp "$stage/window.png" "$project/work/verification/deb-window-$version.png"
# Echte Datenbankänderung plus nachträglich erzeugte Laufzeitdateien: gerade
# diese wurden bisher beim Entfernen übersehen und verhinderten Neuinstallationen.
python3 - "$test_home" <<'RUNTIME'
from contextlib import closing
from pathlib import Path
import json,sqlite3,sys
home=Path(sys.argv[1]);root=home/'.local/share/oesterreichisches-zahlenlotto'
with closing(sqlite3.connect(root/'data/lotto.sqlite3')) as con:
    with con:con.execute("INSERT OR REPLACE INTO metadata VALUES('uninstall_test','changed')")
for name in ('data/lotto.sqlite3-wal','data/lotto.sqlite3-shm','data/backups/lotto-test.sqlite3',
             'data/rejected/test.csv','logs/6aus45_diagnose_test.json','languages/test.json','help/test.html'):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('runtime test')
outside=home/'Documents';outside.mkdir();(outside/'export.csv').write_text('user export')
(outside/'own.sqlite3').write_text('external database')
settings=root/'config/settings.json';config=json.loads(settings.read_text())
config['database']=str(outside/'own.sqlite3');settings.write_text(json.dumps(config))
RUNTIME
run_in_test_home dpkg --log="$stage/dpkg.log" --root="$stage/root" --force-not-root --force-script-chrootless --force-depends --remove oesterreichisches-zahlenlotto
test ! -e "$test_home/Schreibtisch/oesterreichisches-zahlenlotto.desktop"
test ! -e "$stage/root/usr/bin/6aus45"
test ! -e "$stage/root/usr/lib/6aus45"
test ! -e "$stage/root/usr/share/applications/oesterreichisches-zahlenlotto.desktop"
test ! -e "$stage/root/etc/xdg/autostart/oesterreichisches-zahlenlotto-desktop.desktop"
test ! -e "$stage/root/usr/share/pixmaps/6aus45.png"
test ! -e "$test_home/.local/share/oesterreichisches-zahlenlotto"
test -f "$test_home/Documents/export.csv"
test -f "$test_home/Documents/own.sqlite3"
run_in_test_home dpkg --log="$stage/dpkg.log" --root="$stage/root" --force-not-root --force-script-chrootless --force-depends --purge oesterreichisches-zahlenlotto
# Nach Entfernen erneut installieren: der volle mitgelieferte Bestand muss wieder da sein.
run_in_test_home dpkg --log="$stage/dpkg.log" --root="$stage/root" --force-not-root --force-script-chrootless --force-depends -i "$package"
python3 - "$test_home/.local/share/oesterreichisches-zahlenlotto/data/lotto.sqlite3" <<'REINSTALL'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as con:
    assert [con.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('lotto_ziehungen','joker_ziehungen')]==[3683,3574]
print('Neuinstallation: vollständige Datenbank vorhanden.')
REINSTALL
run_in_test_home dpkg --log="$stage/dpkg.log" --root="$stage/root" --force-not-root --force-script-chrootless --force-depends --purge oesterreichisches-zahlenlotto
test ! -e "$test_home/.local/share/oesterreichisches-zahlenlotto"
test ! -e "$test_home/Schreibtisch/oesterreichisches-zahlenlotto.desktop"
printf '\nDEB Installation, Desktop-Start, remove, Neuinstallation und purge ohne Installationsreste erfolgreich. Testordner: %s\n' "$stage"
