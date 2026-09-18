"""Profilbasierte Tippserien ohne Zugriff auf das kombinatorische Universum.

Regeln werden nur im Modus filtered angewendet. Zahlengewichte sind eine
Auswahlpräferenz, niemals eine Vorhersage. Ohne Seed wird SystemRandom benutzt;
seed ist ausschließlich ein ausdrücklich markierter reproduzierbarer Testmodus.
Alle Serien werden erst nach vollständiger Erzeugung atomar gespeichert.
GPL-3.0-only · Josef Lehner.
"""
from collections import Counter
from contextlib import closing
from itertools import combinations,groupby
import datetime as dt
import json
import math
import random
import secrets
from .database import connect
from .schema import now
from .statistics import load_draws
from .joker_statistics import load_joker

PRIMES={2,3,5,7,11,13,17,19,23,29,31,37,41,43}
LOTTO_RULES={'sum','even','low','run','repeat','span','prime','birthday','decades','pairs','unusual','quantiles'}
JOKER_RULES={'sum','different','run','palindrome','suffix','multiplicity'}


def default_profile(game):
    if game not in ('lotto','joker'):raise ValueError('L012: Spiel muss lotto oder joker sein.')
    return {'game':game,'mode':'random','last':0,'from':'','to':'','weekday':-1,'kind':'',
            'weight':0.0,'rules':{}}


def select_draws(draws,profile):
    """Erst Datum/Wochentag/Typ eingrenzen, dann die letzten N Runden auswählen."""
    result=[]
    for draw in draws:
        date=draw.date if hasattr(draw,'date') else draw[1]
        kind=draw.kind if hasattr(draw,'kind') else draw[2]
        if profile.get('from') and date<profile['from']:continue
        if profile.get('to') and date>profile['to']:continue
        weekday=profile.get('weekday',-1)
        if weekday!=-1 and dt.date.fromisoformat(date).weekday()!=weekday:continue
        if profile.get('kind') and kind!=profile['kind']:continue
        result.append(draw)
    limit=profile.get('last',0)
    return result[-limit:] if limit else result


def validate(profile):
    if not isinstance(profile,dict):raise ValueError('L012: Profil muss ein Objekt sein.')
    p={**default_profile(profile.get('game')),**profile}
    if not isinstance(p.get('name',''),str) or len(p.get('name',''))>100:raise ValueError('L012: Ungültiger Profilname.')
    if p['mode'] not in ('random','filtered'):raise ValueError('L012: Unbekannter Modus.')
    if type(p['last']) is not int or p['last']<0:raise ValueError('L012: Ungültiges Zeitfenster.')
    if type(p['weekday']) is not int or p['weekday'] not in range(-1,7):raise ValueError('L012: Ungültiger Wochentag.')
    if not isinstance(p['kind'],str):raise ValueError('L012: Ungültiger Ziehungstyp.')
    for key in ('from','to'):
        if not isinstance(p[key],str):raise ValueError('L012: Datum als TT.MM.JJJJ oder YYYY-MM-DD eingeben.')
        if p[key]:
            try:
                from .date_display import parse_input_date
                p[key]=parse_input_date(p[key])
            except ValueError:raise ValueError('L012: Datum als TT.MM.JJJJ oder YYYY-MM-DD eingeben.') from None
    if p['from'] and p['to'] and p['from']>p['to']:raise ValueError('L012: Beginn liegt nach dem Ende.')
    if type(p['weight']) not in (int,float) or not math.isfinite(p['weight']) or not -5<=p['weight']<=5:
        raise ValueError('L012: Gewichtungsstärke muss zwischen -5 und 5 liegen.')
    rules=p['rules'];allowed=LOTTO_RULES if p['game']=='lotto' else JOKER_RULES
    if not isinstance(rules,dict) or set(rules)-allowed:raise ValueError('L012: Unbekannte Regel für dieses Spiel.')
    bounds={'sum':(21,255) if p['game']=='lotto' else (0,54),'even':(0,6),'low':(0,6),
            'prime':(0,6),'birthday':(0,6),'different':(1,6),'quantiles':(0,100)}
    for key,value in rules.items():
        if key in bounds:
            lo,hi=bounds[key]
            if not isinstance(value,(list,tuple)) or len(value)!=2 or any(type(n) is not int for n in value) or not lo<=value[0]<=value[1]<=hi:
                raise ValueError(f'L012: {key}: Minimum/Maximum von {lo} bis {hi} erforderlich.')
        elif key in ('run','repeat','span','multiplicity'):
            lo,hi={'run':(1,6),'repeat':(0,6),'span':(5,44),'multiplicity':(1,6)}[key]
            if type(value) is not int or not lo<=value<=hi:raise ValueError(f'L012: {key}: Wert von {lo} bis {hi} erforderlich.')
        elif key=='decades':
            if not isinstance(value,list) or len(value)!=5 or any(type(x) is not int or not 0<=x<=6 for x in value) or sum(value)!=6:
                raise ValueError('L012: decades: fünf Anzahlen mit Summe 6 erforderlich.')
        elif key in ('pairs','suffix'):
            if type(value) not in (int,float) or not math.isfinite(value) or not -5<=value<=5:raise ValueError(f'L012: {key}: Stärke von -5 bis 5 erforderlich.')
        elif key=='palindrome':
            if value not in ('allow','avoid','only'):raise ValueError('L012: palindrome: allow, avoid oder only erforderlich.')
        elif key=='unusual' and type(value) is not bool:raise ValueError('L012: unusual: true oder false erforderlich.')
    return p


def quantile(values,percent):
    values=sorted(values);position=(len(values)-1)*percent/100
    low=math.floor(position);high=math.ceil(position)
    return values[low]+(values[high]-values[low])*(position-low)


def longest(values):
    return max((len(list(group)) for _,group in groupby(values)),default=0)


def lotto_run(numbers):
    best=run=1
    for a,b in zip(numbers,numbers[1:]):
        run=run+1 if b==a+1 else 1;best=max(best,run)
    return best


def weighted_choice(rng,population,counts,strength):
    """Geglättete relative Häufigkeiten, begrenzte positive Gewichte."""
    weights=[(counts.get(value,0)+1)**strength for value in population]
    point=rng.random()*sum(weights)
    for value,weight in zip(population,weights):
        point-=weight
        if point<=0:return value
    return population[-1]


def generate(game,count,profile=None,draws=(),max_count=10000,seed=None,cancel=None,progress=lambda a,b:None,max_attempts=None):
    p=validate(profile or default_profile(game))
    if p['game']!=game:raise ValueError('L012: Profil gehört zum anderen Spiel.')
    if type(max_count) is not int or not 1<=max_count<=1000000:raise ValueError('L012: Ungültige Sicherheitsgrenze (1–1000000).')
    if type(count) is not int or not 1<=count<=max_count:raise ValueError(f'L012: Tippanzahl muss zwischen 1 und {max_count} liegen.')
    rng=secrets.SystemRandom() if seed is None else random.Random(seed)
    if game=='joker' and p['mode']=='random':
        values=[]
        for i,n in enumerate(rng.sample(range(1000000),count),1):
            if cancel and cancel.is_set():raise InterruptedError('L013: Tipp-Erstellung abgebrochen; keine Teilserie gespeichert.')
            values.append(f'{n:06d}')
            if i%100==0 or i==count:progress(i,count)
        return values,p
    filtered=p['mode']=='filtered';rules=p['rules'] if filtered else {}
    history=select_draws(draws,p) if filtered else []
    needs_history=filtered and (p['weight'] or any(k in rules for k in ('repeat','pairs','quantiles','suffix')))
    if needs_history and not history:raise ValueError('L012: Keine Ziehungen im gewählten Zeitfenster für die aktivierten Statistikregeln.')
    counts=Counter();positions=[Counter() for _ in range(6)];pairs=Counter();suffix=Counter()
    for draw in history:
        if game=='lotto':counts.update(draw.numbers);pairs.update(combinations(draw.numbers,2))
        else:
            for i,digit in enumerate(draw[3]):positions[i][digit]+=1
            suffix[draw[3][-2:]]+=1
    sums=[sum(d.numbers) for d in history] if game=='lotto' else []
    quantiles=[quantile(sums,q) for q in rules['quantiles']] if 'quantiles' in rules else None
    previous=set(history[-1].numbers) if history and game=='lotto' else set()
    result=[];seen=set();rejects=Counter();attempts=max_attempts or min(2000000,max(10000,count*500))
    for attempt in range(attempts):
        if cancel and cancel.is_set():raise InterruptedError('L013: Tipp-Erstellung abgebrochen; keine Teilserie gespeichert.')
        if attempt%100==0:progress(len(result),count)
        strength=p['weight'] if filtered else 0
        if game=='lotto':
            if strength:
                available=list(range(1,46));chosen=[]
                for _ in range(6):
                    n=weighted_choice(rng,available,counts,strength);chosen.append(n);available.remove(n)
                value=tuple(sorted(chosen))
            else:value=tuple(sorted(rng.sample(range(1,46),6)))
            features={'sum':sum(value),'even':sum(n%2==0 for n in value),'low':sum(n<=22 for n in value),
                      'prime':sum(n in PRIMES for n in value),'birthday':sum(n<=31 for n in value)}
            failures=[key for key in features if key in rules and not rules[key][0]<=features[key]<=rules[key][1]]
            if quantiles and not quantiles[0]<=sum(value)<=quantiles[1]:failures.append('quantiles')
            if 'run' in rules and lotto_run(value)>rules['run']:failures.append('run')
            if 'repeat' in rules and len(set(value)&previous)>rules['repeat']:failures.append('repeat')
            if 'span' in rules and value[-1]-value[0]<rules['span']:failures.append('span')
            if 'decades' in rules and [sum((0 if n<10 else n//10)==i for n in value) for i in range(5)]!=rules['decades']:failures.append('decades')
            if rules.get('unusual') and not (sum(value)<80 or sum(value)>=190 or features['even'] in (0,6) or lotto_run(value)>=4):failures.append('unusual')
            if rules.get('pairs'):
                # Akzeptanzpräferenz mit begrenzter Ablehnung; + häufig, - selten.
                score=sum(pairs[pair] for pair in combinations(value,2))/(15*max(pairs.values(),default=1))
                probability=(.1+.9*(score if rules['pairs']>0 else 1-score))**abs(rules['pairs'])
                if rng.random()>probability:failures.append('pairs')
        else:
            value=''.join(weighted_choice(rng,list('0123456789'),positions[i],strength) if strength else str(rng.randrange(10)) for i in range(6))
            features={'sum':sum(map(int,value)),'different':len(set(value))}
            failures=[key for key in features if key in rules and not rules[key][0]<=features[key]<=rules[key][1]]
            if 'run' in rules and longest(value)>rules['run']:failures.append('run')
            if 'multiplicity' in rules and max(Counter(value).values())>rules['multiplicity']:failures.append('multiplicity')
            pal=value==value[::-1]
            if rules.get('palindrome')=='only' and not pal or rules.get('palindrome')=='avoid' and pal:failures.append('palindrome')
            if rules.get('suffix'):
                score=suffix[value[-2:]]/max(suffix.values(),default=1)
                probability=(.1+.9*(score if rules['suffix']>0 else 1-score))**abs(rules['suffix'])
                if rng.random()>probability:failures.append('suffix')
        if failures:rejects.update(failures);continue
        if value in seen:rejects['duplicates']+=1;continue
        seen.add(value);result.append(value)
        if len(result)==count:progress(count,count);return result,p
    blocked=', '.join(f'{key}: {n}' for key,n in rejects.most_common())
    raise ValueError(f'L012: Nur {len(result)}/{count} eindeutige Tipps nach {attempts} Versuchen. Blockierende Regeln: {blocked}. Filter lockern oder Anzahl reduzieren.')


def create_batch(path,game,count,profile=None,max_count=10000,seed=None,cancel=None,progress=lambda a,b:None):
    history=load_draws(path) if game=='lotto' else load_joker(path)
    values,p=generate(game,count,profile,history,max_count,seed,cancel,progress)
    if cancel and cancel.is_set():raise InterruptedError('L013: Abgebrochen; keine Serie gespeichert.')
    with closing(connect(path)) as con,con:
        con.set_progress_handler(lambda:int(cancel is not None and cancel.is_set()),1000)
        ident=con.execute('INSERT INTO tip_batch(game,created,count,profile,rng_mode,seed) VALUES(?,?,?,?,?,?)',
            (game,now(),count,json.dumps(p,ensure_ascii=False),'SystemRandom' if seed is None else 'TEST',seed)).lastrowid
        con.executemany('INSERT INTO batch_tip VALUES(?,?,?)',((ident,i,v if isinstance(v,str) else ' '.join(f'{n:02d}' for n in v)) for i,v in enumerate(values,1)))
        if cancel and cancel.is_set():raise InterruptedError('L013: Abgebrochen; keine Serie gespeichert.')
    return get_batch(path,ident)


def get_batch(path,ident):
    with closing(connect(path,create=False)) as con:
        row=con.execute('SELECT * FROM tip_batch WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('L012: Tippserie nicht vorhanden; Historie aktualisieren.')
        result=dict(row);result['profile']=json.loads(result['profile'])
        result['tips']=[r[0] for r in con.execute('SELECT value FROM batch_tip WHERE batch_id=? ORDER BY position',(ident,))]
        return result


def list_batches(path,game):
    with closing(connect(path,create=False)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='tip_batch'").fetchone():return []
        return [dict(r) for r in con.execute('SELECT id,created,count,rng_mode FROM tip_batch WHERE game=? ORDER BY id DESC',(game,))]


def profiles(path,game):
    with closing(connect(path,create=False)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='stat_profile'").fetchone():return []
        return [(r['name'],json.loads(r['settings'])) for r in con.execute('SELECT * FROM stat_profile WHERE game=? ORDER BY name',(game,))]


def save_profile(path,name,profile):
    p=validate(profile)
    if not name.strip() or len(name)>100:raise ValueError('L012: Profilname mit 1 bis 100 Zeichen erforderlich.')
    p['name']=name.strip()
    with closing(connect(path)) as con,con:
        con.execute('INSERT INTO stat_profile(game,name,settings,updated) VALUES(?,?,?,?) ON CONFLICT(game,name) DO UPDATE SET settings=excluded.settings,updated=excluded.updated',
                    (p['game'],name.strip(),json.dumps(p,ensure_ascii=False),now()))
        con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('selected_profile_'+p['game'],name.strip()))


def delete_profile(path,game,name):
    with closing(connect(path)) as con,con:
        con.execute('DELETE FROM stat_profile WHERE game=? AND name=?',(game,name))
        con.execute('DELETE FROM metadata WHERE key=? AND value=?',('selected_profile_'+game,name))


def selected_profile(path,game,name=None):
    with closing(connect(path,create=False)) as con:
        if name is None:
            row=con.execute('SELECT value FROM metadata WHERE key=?',('selected_profile_'+game,)).fetchone()
            name=row[0] if row else None
    choices=dict(profiles(path,game))
    if name not in choices:raise ValueError('L012: Kein gültiges eingestelltes Profil. Zuerst ein Profil speichern oder laden.')
    return validate(choices[name])
