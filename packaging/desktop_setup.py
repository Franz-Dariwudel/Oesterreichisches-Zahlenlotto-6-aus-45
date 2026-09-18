#!/usr/bin/python3
"""Desktop-Starter benutzerbezogen einrichten und angelegte Dateien erfassen."""
import hashlib, json, os, pwd, shutil, subprocess, sys
from pathlib import Path
from seed_database import install_database
BASE=Path(__file__).resolve().parent
PREFIX=BASE.parents[2]
NAME='oesterreichisches-zahlenlotto'

def user_setup(remove=False):
    home=Path.home(); state=home/'.local/share'/NAME
    journal=state/'installation.json'
    if remove:
        if journal.is_file():
            saved=json.loads(journal.read_text())
            seed=saved.get('seed_database',{})
            database=Path(seed.get('path','/nonexistent'))
            if database.is_relative_to(state) and database.is_file() and not database.is_symlink():
                with database.open('rb') as stream:unchanged=hashlib.file_digest(stream,'sha256').hexdigest()==seed['sha256']
                if unchanged and not Path(str(database)+'-wal').exists():database.unlink()
            for name in saved.get('files',[]):
                path=Path(name)
                if path.is_relative_to(home) and (path.is_symlink() or not path.is_dir()):path.unlink(missing_ok=True)
            journal.unlink()
        # Laufzeitdatenbanken bleiben erhalten. Nur leere eigene Ordner entfernen.
        if state.exists():
            for path in sorted(state.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if path.is_dir() and not path.is_symlink():
                    try:path.rmdir()
                    except OSError:pass
            try:state.rmdir()
            except OSError:pass
        return
    state.mkdir(parents=True,exist_ok=True)
    install_database(BASE,state)
    data=json.loads(journal.read_text()) if journal.exists() else {'files':[]}
    try:
        desktop=Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
    except (OSError,subprocess.SubprocessError):desktop=home/'Desktop'
    if not desktop.is_absolute() or desktop==home:
        print('Desktop-Starter ausstehend: Kein separater Desktopordner eingerichtet.',file=sys.stderr);return
    desktop.mkdir(parents=True,exist_ok=True)
    target=desktop/(NAME+'.desktop')
    if target.exists() and str(target) not in data['files']:
        print('Vorhandener fremder Desktop-Starter bleibt erhalten:',target,file=sys.stderr);return
    entry=(BASE/'launcher.desktop').read_text().replace('/usr/bin/6aus45',str(PREFIX/'usr/bin/6aus45')).replace('Icon=6aus45','Icon='+str(PREFIX/'usr/share/pixmaps/6aus45.png'))
    target.write_text(entry);target.chmod(0o755)
    subprocess.run(['gio','set',str(target),'metadata::trusted','true'],capture_output=True)
    if str(target) not in data['files']:data['files'].append(str(target))
    journal.write_text(json.dumps(data,indent=2))
    print('Desktop-Starter:',target)

def system_setup(remove=False):
    # Beim Entfernen alle Benutzer berücksichtigen, die einen Installationsnachweis besitzen.
    if remove:
        users=[p for p in pwd.getpwall() if p.pw_uid>=1000 and (Path(p.pw_dir)/'.local/share'/NAME/'installation.json').is_file()]
    else:
        users=[]
        result=subprocess.run(['loginctl','list-sessions','--no-legend'],capture_output=True,text=True)
        for line in result.stdout.splitlines():
            sid=line.split()[0]
            props=subprocess.run(['loginctl','show-session',sid,'-p','Type','-p','Name','-p','Active'],capture_output=True,text=True).stdout
            info=dict(x.split('=',1) for x in props.splitlines() if '=' in x)
            if info.get('Type') in ('x11','wayland') and info.get('Active')=='yes':
                user=pwd.getpwnam(info['Name'])
                if user.pw_uid>=1000 and user not in users:users.append(user)
        if len(users)!=1:
            print('Desktop-Einrichtung erfolgt bei der nächsten grafischen Anmeldung.');return
    for user in users:
        env=dict(os.environ,HOME=user.pw_dir,XDG_RUNTIME_DIR=f'/run/user/{user.pw_uid}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{user.pw_uid}/bus')
        subprocess.run(['runuser','-u',user.pw_name,'--','/usr/bin/python3','-B',str(__file__),'--remove' if remove else '--user'],env=env,check=True)

if __name__=='__main__':
    if '--system' in sys.argv:system_setup('--remove' in sys.argv)
    else:user_setup('--remove' in sys.argv)
