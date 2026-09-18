#!/bin/bash
set -euo pipefail
project=$(cd "$(dirname "$0")/.." && pwd)
stage=$(mktemp -d "$project/work/deb-test-XXXXXX")
export HOME="$stage/home" XDG_CONFIG_HOME="$stage/home/.config"
unset SUDO_UID PKEXEC_UID
mkdir -p "$HOME/.config" "$HOME/Schreibtisch" "$stage/root/var/lib/dpkg"
printf 'XDG_DESKTOP_DIR="$HOME/Schreibtisch"\n' > "$HOME/.config/user-dirs.dirs"
touch "$stage/root/var/lib/dpkg/status"
dpkg --log="$stage/dpkg.log" --root="$stage/root" --force-not-root --force-script-chrootless --force-depends -i "$project/auslieferung/oesterreichisches-zahlenlotto_1.0.27_amd64.deb"
dpkg-query --admindir="$stage/root/var/lib/dpkg" -W -f='${Status}\n' oesterreichisches-zahlenlotto
test -x "$HOME/Schreibtisch/oesterreichisches-zahlenlotto.desktop"
desktop-file-validate "$HOME/Schreibtisch/oesterreichisches-zahlenlotto.desktop"
icon=$(sed -n 's/^Icon=//p' "$HOME/Schreibtisch/oesterreichisches-zahlenlotto.desktop")
test -s "$icon"
python3 - "$HOME/.local/share/oesterreichisches-zahlenlotto/data/lotto.sqlite3" <<'CHECK'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
    counts=[db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('lotto_ziehungen','joker_ziehungen')]
    assert counts==[3683,3574],counts
    print('Installierte Datenbank: Lotto',counts[0],'Joker',counts[1])
CHECK
cmp "$icon" "$project/resources/icon.png"
"$stage/root/usr/bin/6aus45" --version
set +e
timeout 7 "$stage/root/usr/bin/6aus45" > "$stage/gui.log" 2>&1
result=$?
set -e
test "$result" = 124
cat "$stage/gui.log"
dpkg --log="$stage/dpkg.log" --root="$stage/root" --force-not-root --force-script-chrootless --force-depends --purge oesterreichisches-zahlenlotto
test ! -e "$HOME/Schreibtisch/oesterreichisches-zahlenlotto.desktop"
test ! -e "$stage/root/usr/bin/6aus45"
test ! -e "$stage/root/usr/lib/6aus45"
test ! -e "$stage/root/usr/share/applications/oesterreichisches-zahlenlotto.desktop"
test ! -e "$stage/root/etc/xdg/autostart/oesterreichisches-zahlenlotto-desktop.desktop"
printf '\nVerbleibende Benutzerdateien (Datenbank erhalten):\n'
find "$HOME/.local/share/oesterreichisches-zahlenlotto" -type f 2>/dev/null || true
printf '\nDEB Installation, Start und Deinstallation erfolgreich. Testordner: %s\n' "$stage"
