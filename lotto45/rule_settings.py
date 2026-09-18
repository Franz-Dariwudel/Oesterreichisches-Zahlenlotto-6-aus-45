"""Gespeicherte Tippfilterwerte; Aktivierung erfolgt getrennt im Tippformular.

Die Werte liegen je Spiel in config/settings.json. Statistikseiten ändern nur
ihre eigenen Regeln. Gespeicherte Tippserien behalten ihren Profilschnappschuss.
"""
from copy import deepcopy
from . import tips,settings

SCOPE=('last','from','to','weekday','kind')
DEFAULTS={
    'lotto':{'sum':[90,180],'quantiles':[10,90],'even':[2,4],'low':[2,4],
             'run':2,'repeat':2,'span':25,'prime':[0,6],'birthday':[0,6],
             'decades':[1,2,1,1,1],'pairs':1.0,'unusual':True},
    'joker':{'sum':[15,40],'different':[3,6],'run':2,'multiplicity':2,
             'palindrome':'avoid','suffix':1.0}}
PAGES={'sum':'sums','quantiles':'sums','even':'parity','low':'low_high',
       'run':'neighbors','repeat':'repeats','span':'ranges','prime':'patterns',
       'birthday':'patterns','decades':'patterns','pairs':'pairs','unusual':'patterns',
       'weight':'numbers'}


def page_for(game,key):
    return ('joker' if key=='weight' else 'patterns') if game=='joker' else PAGES[key]


def load(config,game):
    p=tips.default_profile(game);p.update(mode='filtered',weight=1.0,rules=deepcopy(DEFAULTS[game]))
    try:
        saved=config.get('tip_rule_settings',{}).get(game,{})
        if not isinstance(saved,dict):raise ValueError('Objekt erwartet')
        p.update({k:saved[k] for k in (*SCOPE,'weight') if k in saved})
        p['rules'].update(saved.get('rules',{}))
        return tips.validate(p)
    except (ValueError,TypeError,AttributeError) as error:
        raise ValueError(f'L004: Tippfilter-Einstellungen ({game}) ungültig: {error}. config/settings.json prüfen.') from error


def save(app,game,profile):
    """Erst erfolgreich schreiben, dann den aktiven Konfigurationsstand ändern."""
    p=tips.validate(profile)
    if p['game']!=game:raise ValueError('L012: Falsches Spiel für Tippfilter.')
    config=deepcopy(app.config)
    config.setdefault('tip_rule_settings',{})[game]={k:deepcopy(p[k]) for k in (*SCOPE,'weight','rules')}
    try:settings.save(config)
    except OSError as error:raise ValueError(f'L004: Tippfilter konnten nicht gespeichert werden: {error}. Schreibrechte für config prüfen.') from error
    app.config=config


def parse(key,text):
    if key in ('sum','quantiles','even','low','prime','birthday','different','decades'):
        return [int(n.strip()) for n in text.split(',')]
    if key in ('weight','pairs','suffix'):return float(text)
    return int(text)


def describe(value):
    return ', '.join(map(str,value)) if isinstance(value,list) else str(value)
