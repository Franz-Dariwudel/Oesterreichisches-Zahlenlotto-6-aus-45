"""Öffentliche Release-Metadaten laden; das Datenbankarchiv wird nicht geladen."""
import json
from datetime import datetime
from urllib.request import Request, urlopen

REPOSITORY = 'Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45'
DOWNLOAD_URL = f'https://github.com/{REPOSITORY}/releases/latest/download/lotto-datenbank.zip'


def release_info():
    """Nur die passende ZIP-Datei eines veröffentlichten Releases auswerten."""
    request = Request(f'https://api.github.com/repos/{REPOSITORY}/releases/latest',
                      headers={'Accept': 'application/vnd.github+json', 'User-Agent': '6aus45'})
    with urlopen(request, timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('Release metadata too large')
    return parse_release(json.loads(raw))


def parse_release(data):
    """Fehlende oder ungültige Angaben nicht als bestätigte Dateidaten anzeigen."""
    asset = next(a for a in data['assets'] if a.get('name') == 'lotto-datenbank.zip')
    size = asset['size']
    if type(size) is not int or size <= 0 or asset.get('state') != 'uploaded':
        raise ValueError('Invalid release asset')
    published = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00')).astimezone()
    version = data['tag_name']
    if not isinstance(version, str) or not version.strip():
        raise ValueError('Missing release version')
    return {'name': asset['name'], 'size': f'{size / 1024 / 1024:.2f} MiB ({size:,} B)',
            'version': version, 'published': published.strftime('%d.%m.%Y %H:%M %Z')}
