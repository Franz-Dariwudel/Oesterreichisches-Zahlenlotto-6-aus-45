"""Eigene temporäre Arbeitsbereiche mit Dateisperre statt unsicherer PID-Prüfung.

Nur Verzeichnisse des aktuellen Benutzers mit passender Markierung und einer
nicht gehaltenen flock-Sperre werden beim Start aufgeräumt. Symlinks bleiben.
"""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import os
import shutil
import tempfile

PREFIX='lotto_joker_'
MARKER='6aus45-owned-v1'


@contextmanager
def workspace(parent=None):
    folder=Path(tempfile.mkdtemp(prefix=PREFIX,dir=parent or '/tmp'))
    try:
        with (folder/'.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            (folder/'.owner').write_text(MARKER)
            yield folder
    finally:shutil.rmtree(folder)


def cleanup(parent='/tmp'):
    removed=[]
    for folder in Path(parent).glob(PREFIX+'*'):
        try:
            if folder.is_symlink() or not folder.is_dir() or folder.stat().st_uid!=os.getuid():continue
            marker=folder/'.owner';lockpath=folder/'.lock'
            if marker.is_symlink() or lockpath.is_symlink() or marker.read_text()!=MARKER:continue
            fd=os.open(lockpath,os.O_RDWR|os.O_NOFOLLOW)
            with os.fdopen(fd,'r+') as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:continue
                shutil.rmtree(folder);removed.append(str(folder))
        except (OSError,UnicodeError):continue
    return removed
