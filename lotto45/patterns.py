"""Zusätzliche deskriptive Lotto-/Joker-Muster aus Kapitel 7 und 8 des Konzepts.

Chi-Quadrat wird als deskriptive Abweichungszahl ohne unabhängige p-Werte
angegeben, weil die sechs Hauptzahlen einer Ziehung nicht unabhängig sind.
"""
from collections import Counter
from itertools import combinations
import datetime as dt
import math
from .statistics import Table


def analyse(draws,game):
    # Lokaler Import vermeidet einen Kreis mit der Generator-Regelbibliothek.
    from .tips import PRIMES,longest,lotto_run,quantile
    metrics={};series={};dates=[]
    def add(key,value):series.setdefault(key,Counter())[value]+=1
    positions=[[0]*10 for _ in range(6)];transitions=[[0]*10 for _ in range(10)]
    weekdays=[[0]*10 for _ in range(7)];hits=Counter();centrality=Counter();patterns=[]
    for draw in draws:
        date=draw.date if game=='lotto' else draw[1];dates.append(date)
        if game=='lotto':
            ns=draw.numbers;hits.update(ns)
            add('prime',sum(n in PRIMES for n in ns));add('birthday',sum(n<=31 for n in ns))
            add('mirror',sum(a+b==46 for a,b in combinations(ns,2)))
            add('span',ns[-1]-ns[0]);add('run',lotto_run(ns));add('neighbors',sum(b-a==1 for a,b in zip(ns,ns[1:])))
            gaps=[b-a for a,b in zip(ns,ns[1:])]
            add('arithmetic',len(set(gaps))==1)
            for gap in gaps:add('gaps',gap)
            for a,b in combinations(ns,2):centrality[a]+=1;centrality[b]+=1
            for n in ns:add('decades',0 if n<10 else n//10)
        else:
            value=draw[3];digits=list(map(int,value));counter=Counter(value)
            add('sum',sum(digits));add('different',len(counter));add('adjacent',sum(a==b for a,b in zip(value,value[1:])))
            add('run',longest(value));add('symmetry',sum(value[i]==value[-i-1] for i in range(3)))
            add('entropy',round(-sum((n/6)*math.log2(n/6) for n in counter.values()),3))
            add('parity','-'.join('E' if n%2==0 else 'O' for n in digits))
            for a,b in zip(digits,digits[1:]):transitions[a][b]+=1;add('differences',b-a)
            for position,digit in enumerate(digits):positions[position][digit]+=1;weekdays[dt.date.fromisoformat(date).weekday()][digit]+=1
            for size in (1,2,3):add('suffix'+str(size),value[-size:])
            patterns.append((date,value,int(value==value[::-1]),sum(value[i]==value[-i-1] for i in range(3))))
    tables=[Table('pattern_'+key,[('pattern_value','text'),('s_hits','int')],sorted(counter.items())) for key,counter in series.items()]
    if game=='lotto':
        expected=len(draws)*6/45
        sums=[sum(d.numbers) for d in draws]
        for q in (10,25,50,75,90):metrics['quantile_'+str(q)]=quantile(sums,q) if sums else None
        metrics['chi_square']=sum((hits[n]-expected)**2/expected for n in range(1,46)) if expected else None
        tables.append(Table('pattern_centrality',[('s_number','number'),('pattern_strength','int')],[(n,centrality[n]) for n in range(1,46)]))
    else:
        tables.append(Table('pattern_palindromes',[('s_date','date'),('j_number','text'),('pattern_palindrome','int'),('pattern_symmetry','int')],patterns))
        tables.extend([Table('pattern_positions',[('j_position','int'),('j_digit','int'),('s_hits','int')],[(i+1,j,n) for i,row in enumerate(positions) for j,n in enumerate(row)]),
                       Table('pattern_transitions',[('pattern_from','int'),('pattern_to','int'),('s_hits','int')],[(i,j,n) for i,row in enumerate(transitions) for j,n in enumerate(row)]),
                       Table('pattern_weekdays',[('pattern_weekday','int'),('j_digit','int'),('s_hits','int')],[(i,j,n) for i,row in enumerate(weekdays) for j,n in enumerate(row)])])
    return {'kind':'patterns','count':len(draws),'available':len(draws),'first':min(dates,default=None),'last':max(dates,default=None),
            'metrics':[('pattern_'+key,value,'float') for key,value in metrics.items()],'tables':tables,'series':series,
            'positions':positions,'transitions':transitions,'weekdays':weekdays}


def chart(report,key):
    common={'kind':key,'count':report['count'],'x_title':'pattern_value','y_title':'s_hits'}
    if key in ('positions','transitions','weekdays'):
        matrix=report[key]
        return {**common,'type':'heatmap','matrix':matrix,'xlabels':list(map(str,range(10))),
                'ylabels':list(map(str,range(1,7))) if key=='positions' else list(map(str,range(len(matrix))))}
    counter=report['series'][key];keys=sorted(counter)
    return {**common,'type':'bar','labels':list(map(str,keys)),'values':[counter[n] for n in keys]}
