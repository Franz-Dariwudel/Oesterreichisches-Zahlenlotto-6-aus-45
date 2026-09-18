"""Besitznachweis und vollständige Entfernung der benutzerbezogenen DEB-Ausgabe.

Die privaten Laufzeitordner gehören zur Installation: auch nachträglich angelegte
Datenbanken, WAL-Dateien, Sicherungen, Downloads und Berichte werden entfernt.
Vor der ersten Einrichtung vorhandene Dateien bleiben erhalten. Außerhalb dieser
Ordner werden ausschließlich nachweislich eigene Desktop-Starter entfernt.
"""
import json
import os
from pathlib import Path
import tempfile

NAME = 'oesterreichisches-zahlenlotto'
FOLDERS = {'lotto45', 'resources', 'languages', 'help', 'vendor', 'config', 'logs', 'data'}


def inventory(root):
    """Dateien und Ordner erfassen, Verzeichnis-Symlinks niemals verfolgen."""
    if root.is_symlink():
        raise RuntimeError('L006: Installationsordner ist ein symbolischer Link: ' + str(root))
    if not root.exists():
        return
    def failed(error):
        raise error
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        for name in dirs + files:
            yield Path(parent) / name


def save_journal(root, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root, prefix='.installation-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(root / 'installation.json')
        finally:
            temporary.unlink(missing_ok=True)


def prepare_state(root):
    """Einmal vor der ersten Dateianlage bestehende Dateien unter Schutz stellen."""
    root = Path(root)
    if root.is_symlink():
        raise RuntimeError('L006: Installationsordner ist ein symbolischer Link: ' + str(root))
    journal = root / 'installation.json'
    previous = journal.is_file()
    data = json.loads(journal.read_text()) if previous else {'files': []}
    if data.get('ownership_version') == 1:
        return data
    protected = []
    for path in inventory(root):
        relative = path.relative_to(root)
        # Alte DEB-Journale erfassten Laufzeitdateien noch nicht. Die eindeutig
        # programmeigenen Unterordner gehören auch bei deren Migration dazu.
        if previous and (relative.parts[0] in FOLDERS or relative.name == 'installation.json'):
            continue
        protected.append(str(relative))
    data.update(ownership_version=1, preserved_paths=protected)
    root.mkdir(parents=True, exist_ok=True)
    save_journal(root, data)
    return data


def active_processes(root):
    """Laufende installierte Ausgabe erkennen, damit sie keine Reste neu anlegt."""
    found = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            args = (process / 'cmdline').read_bytes().split(b'\0')
            if any(args[n:n+2] == [b'-m', b'lotto45'] for n in range(len(args)-1)) and (process / 'cwd').resolve() == root.resolve():
                found.append(int(process.name))
        except (OSError, RuntimeError):
            continue
    return found


def remove_state(root, home, executable):
    """Nur eigene Dateien löschen; Löschfehler mit Pfad melden und Journal behalten."""
    root, home = Path(root), Path(home)
    running = active_processes(root)
    if running:
        raise RuntimeError('L006: Programm vor der Deinstallation schließen. Prozesse: ' + ', '.join(map(str, running)))
    journal = root / 'installation.json'
    if not journal.is_file():
        if root.exists():
            raise RuntimeError('L006: Installationsnachweis fehlt; Ordner nicht sicher zuordenbar: ' + str(root))
        return
    saved = prepare_state(root)
    protected = set(saved['preserved_paths'])
    errors = []
    # Externe Pfade im Journal sind keine allgemeine Löschberechtigung.
    for name in saved.get('files', []):
        path = Path(name)
        if path.name != NAME + '.desktop' or not path.is_absolute() or '..' in path.parts:
            continue
        if not path.parent.resolve().is_relative_to(home.resolve()) or path.is_symlink():
            continue
        try:
            if path.is_file() and ('Exec=' + str(executable)) in path.read_text().splitlines():
                path.unlink()
        except OSError as error:
            errors.append(f'{path}: {error}')
    paths = sorted(inventory(root), key=lambda path: len(path.parts), reverse=True)
    for path in paths:
        relative = path.relative_to(root)
        if str(relative) in protected or relative.parts[0] not in FOLDERS:
            continue
        try:
            if path.is_symlink() or not path.is_dir():
                path.unlink()
            elif not any(path.iterdir()):
                path.rmdir()
        except OSError as error:
            errors.append(f'{path}: {error}')
    if errors:
        raise RuntimeError('L006: Deinstallation unvollständig:\n' + '\n'.join(errors))
    journal.unlink()
    if not any(root.iterdir()):
        root.rmdir()
    else:
        print('Bereits vorhandene oder fremde Dateien bleiben erhalten:', root)
