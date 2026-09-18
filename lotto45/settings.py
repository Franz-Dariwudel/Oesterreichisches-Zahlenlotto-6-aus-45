"""Dynamische Sprachen und verlustfreie Ergänzung aus einer Projekt-GitHub-Quelle."""
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parent.parent


def catalogs(root=ROOT):
    result={}
    for path in (root/'languages').glob('*.json'):
        try:
            value=json.loads(path.read_text())
            if not isinstance(value,dict) or not value or any(not isinstance(v,str) for v in value.values()): raise ValueError('Ungültiger Sprachkatalog')
            result[path.stem]=value
        except (ValueError,OSError): logging.exception('L004: Sprachdatei ungültig: %s',path)
    return result


def language_options(root=ROOT):
    """Lokale und zum Download angebotene Sprachen dynamisch zusammenführen."""
    local=catalogs(root)
    names={code:value.get('language_name',code) for code,value in local.items()}
    try:
        index=json.loads((root/'resources/language-index.json').read_text())
        for code in index['languages']:
            if isinstance(code,str) and re.fullmatch(r'[a-z]{2}(?:-[A-Za-z]{2})?',code):
                name=index.get('names',{}).get(code,code)
                names.setdefault(code,name if isinstance(name,str) else code)
    except (OSError,ValueError,KeyError,TypeError):
        logging.exception('L005: Verfügbare Sprachen konnten nicht gelesen werden')
    return sorted(names.items())


def load(root=None):
    p=(Path(root) if root is not None else ROOT)/'config/settings.json'
    defaults={'language':'de','repository':'Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45','max_tips':10000}
    if not p.exists():
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(defaults,indent=2),encoding='utf-8')
        logging.warning('L004: Fehlende Konfiguration mit Standards angelegt: %s',p)
        return defaults
    try:
        value=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(value,dict):raise ValueError('Objekt erwartet')
        merged={**defaults,**value}
        if type(merged['max_tips']) is not int or not 1<=merged['max_tips']<=1000000:raise ValueError('max_tips muss 1–1000000 sein')
        return merged
    except (ValueError,UnicodeError) as error:
        import datetime
        broken=p.with_name(p.name+'.'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.broken')
        p.rename(broken);p.write_text(json.dumps(defaults,indent=2),encoding='utf-8')
        logging.error('L004: Ungültige Konfiguration nach %s gesichert: %s',broken,error)
        return {**defaults,'recovery_notice':f'L004: {broken.name}: {error}'}


def database_path(config,root=None):
    """Gespeicherte Archivauswahl; ohne Auswahl gilt die ursprüngliche Standarddatei."""
    root=Path(root) if root is not None else ROOT
    value=config.get('database')
    if value is None:return root/'data/lotto.sqlite3'
    if not isinstance(value,str) or not value.strip() or '\x00' in value:
        raise ValueError('L004: Ungültiger Datenbankpfad in config/settings.json')
    path=Path(value).expanduser()
    return path if path.is_absolute() else root/path


def save(value):
    path=ROOT/'config/settings.json'; path.parent.mkdir(exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)); tmp.replace(path)


def help_images(text):
    """Nur lokale PNG-Hilfebilder aus dem eigenen images-Unterordner zulassen."""
    from html.parser import HTMLParser
    class Images(HTMLParser):
        def __init__(self):super().__init__();self.paths=[]
        def handle_starttag(self,tag,attrs):
            if tag!='img':return
            src=dict(attrs).get('src','')
            if not re.fullmatch(r'images/[A-Za-z0-9_-]+\.png',src):
                raise ValueError('L005: Ungültiger Hilfebildpfad')
            if src not in self.paths:self.paths.append(src)
    parser=Images();parser.feed(text);return parser.paths


def help_complete(root,code):
    try:
        text=(root/'help'/f'{code}.html').read_text()
        return all((root/'help'/name).is_file() for name in help_images(text))
    except (OSError,ValueError):return False


def download(repository, code, root=ROOT, download_dir=None, fetch=None):
    """Nur fehlende Dateien installieren. Keine eigene Übersetzung überschreiben.

    repository enthält owner/repo; verfügbare Sprachcodes stehen in der
    resources/language-index.json im main-Zweig dieses Projekts. Ohne veröffentlichte
    Projektquelle wird die Aktion sichtbar abgelehnt.
    """
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository): raise ValueError('L005: GitHub-Projektquelle fehlt (owner/repository)')
    if not re.fullmatch(r'[a-z]{2}(?:-[A-Za-z]{2})?',code): raise ValueError('L005: Ungültiger Sprachcode')
    if fetch is None:
        def fetch(url):
            with urllib.request.urlopen(url,timeout=25) as r:
                data=r.read(2_000_001)
                if len(data)>2_000_000: raise ValueError('L005: Datei zu groß')
                return data
    base=f'https://raw.githubusercontent.com/{repository}/main/'
    # Datenindex gehört zum selben Projekt, keine fremden Download-URLs.
    available=json.loads(fetch(base+'resources/language-index.json'))
    if code not in available.get('languages',[]): raise ValueError('L005: Sprache nicht in der Projektquelle verfügbar')
    if download_dir is None:
        download_dir=download_directory()
    download_dir=Path(download_dir); download_dir.mkdir(parents=True,exist_ok=True)
    staged=[]; installed=[]; help_text=None
    with tempfile.TemporaryDirectory(prefix='6aus45-sprachen-',dir=download_dir) as tmp:
        for folder,extension in [('languages','json'),('help','html')]:
            target=root/folder/f'{code}.{extension}'
            if target.exists():
                if extension=='html':help_text=target.read_text(encoding='utf-8')
                continue
            data=fetch(base+f'{folder}/{code}.{extension}')
            text=data.decode('utf-8')
            if extension=='json':
                value=json.loads(text)
                # Ältere veröffentlichte Kataloge sind gültig; neue Schlüssel fallen auf Englisch zurück.
                required={'language_name','language','save'}
                if not isinstance(value,dict) or not required.issubset(value) or not value or any(not isinstance(v,str) for v in value.values()): raise ValueError('L005: Sprachdatei unvollständig')
            elif not re.search(r'<html\s[^>]*lang=[\"\']'+re.escape(code)+r'[\"\']',text,re.I) or '</html>' not in text.lower():
                raise ValueError('L005: HTML-Hilfe fehlt oder falsche Sprache')
            if extension=='html':help_text=text
            temporary=Path(tmp)/f'{code}.{extension}'; temporary.write_bytes(data); staged.append((target,temporary))
        # Bilder gehören zum gleichen atomaren Installationsvorgang wie die HTML-Hilfe.
        for name in help_images(help_text or ''):
            target=root/'help'/name
            if target.exists():continue
            data=fetch(base+'help/'+name)
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('L005: Ungültiges Hilfebild')
            temporary=Path(tmp)/Path(name).name;temporary.write_bytes(data);staged.append((target,temporary))
        try:
            for target,temporary in staged:
                target.parent.mkdir(parents=True,exist_ok=True)
                try:
                    with target.open('xb') as out:
                        installed.append(target)
                        out.write(temporary.read_bytes())
                except FileExistsError: pass
        except OSError:
            for target in installed: target.unlink(missing_ok=True)
            raise
    return len(installed)


def download_directory():
    """Persönlichen Downloadordner ermitteln, auch nach einem Adminstart."""
    import subprocess,pwd
    uid=os.environ.get('SUDO_UID') or os.environ.get('PKEXEC_UID')
    home=Path(pwd.getpwuid(int(uid)).pw_dir) if uid and uid.isdigit() else Path.home()
    download_dir=home/'Downloads'
    if home==Path.home():
        try:
            x=subprocess.run(['xdg-user-dir','DOWNLOAD'],capture_output=True,text=True,check=True).stdout.strip()
            if x: download_dir=Path(x)
        except (OSError,subprocess.SubprocessError): pass
    return download_dir
