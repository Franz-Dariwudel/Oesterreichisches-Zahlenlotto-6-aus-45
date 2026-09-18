"""Deskriptive Lotto-Statistik ohne Änderungen am Ziehungsarchiv.

Nur importierte Hauptzahlen werden ausgewertet; Zusatzzahlen separat.
Abstände zwischen Treffern zählen Ziehungsschritte (direkt danach = 1).
Historische Pausen zählen die dazwischenliegenden Ziehungen (Abstand - 1).
Bei nie beobachteten Zahlen ist die aktuelle Pause eine Untergrenze.
Die erste ausgewählte Ziehung wird, soweit vorhanden, mit ihrem Vorgänger
außerhalb des Zeitfensters verglichen. Gleiche Tage sind nach ID geordnet.
"""
from collections import Counter,defaultdict
from contextlib import closing
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
import math
import sqlite3
import statistics as stdstats

WINDOWS=(10,20,50,100,500)
KINDS=('overview','numbers','expectation','draws','ranges','parity','low_high',
       'sums','pairs','triples','neighbors','repeats','endings','gaps','periods','rankings','charts')
CHARTS=('frequency','pause','timeline','sums','parity','low_high','heatmap','deviation','rolling','zscore')
RANGES=((1,9),(10,19),(20,29),(30,39),(40,45))
SUM_BINS=('<80','80–99','100–119','120–139','140–159','160–179','≥180')


@dataclass(frozen=True)
class Draw:
    id:int
    date:str
    kind:str
    numbers:tuple
    bonus:int


@dataclass
class Table:
    title:str
    columns:list  # (Übersetzungsschlüssel, Anzeigeformat); Zeilen behalten echte Zahlen.
    rows:list
    filter_column:int|None=None


def load_draws(path,cancel=None):
    """Nur die kleinen Ziehungstabellen lesen; die 8 Mio. Tipps nicht durchlaufen."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=60)) as con:
        if cancel:con.set_progress_handler(lambda:int(cancel.is_set()),1000)
        con.execute('BEGIN')
        rows=con.execute('SELECT d.id,d.datum,d.kennung,t.n1,t.n2,t.n3,t.n4,t.n5,t.n6,d.zusatzzahl '
                         'FROM lotto_ziehungen d JOIN lotto_tipps t ON t.id=d.tipp_id ORDER BY d.datum,d.id')
        return [Draw(r[0],r[1],r[2],tuple(r[3:9]),r[9]) for r in rows]


def pct(n,total):return 100*n/total if total else None
def mean(values):return stdstats.mean(values) if values else None
def sum_bin(value):return 0 if value<80 else min(6,1+(value-80)//20)


class Analysis:
    """Gemeinsam berechnete Kennzahlen für Tabellen und Diagramme."""
    def __init__(self,draws,limit=0,cancel=None):
        if type(limit) is not int or limit<0:raise ValueError('L002: Ungültiges Statistik-Zeitfenster')
        self.all_draws=sorted(draws,key=lambda d:(d.date,d.id))
        self.draws=self.all_draws[-limit:] if limit else self.all_draws[:]
        self.n=len(self.draws);self.limit=limit;self.details=[]
        self.hits={n:[] for n in range(1,46)};self.bonus=Counter()
        self.pairs=Counter();self.triples=Counter();self.pair_last={};self.triple_last={}
        self.gaps=Counter();self.gap_last={};self.runs=[]
        self.repeat_counts=Counter();self.repeat_last={};self.repeat_numbers=Counter();self.comparisons=0
        self.ending_hits=Counter();self.ending_draws=Counter();self.ending_multiple=Counter()
        self.ending_combos=Counter();self.ending_last={}
        start=len(self.all_draws)-self.n
        for i,d in enumerate(self.draws):
            if cancel and cancel.is_set():raise InterruptedError('Statistik abgebrochen')
            ns=d.numbers
            for n in ns:self.hits[n].append(i)
            self.bonus[d.bonus]+=1
            for size,counts,last in ((2,self.pairs,self.pair_last),(3,self.triples,self.triple_last)):
                for group in combinations(ns,size):counts[group]+=1;last[group]=i
            gaps=[b-a for a,b in zip(ns,ns[1:])]
            self.gaps.update(gaps)
            for gap in gaps:self.gap_last[gap]=i
            neighbors=[(a,b) for a,b in zip(ns,ns[1:]) if b-a==1]
            run=[ns[0]];runs=[]
            for value in ns[1:]:
                if value==run[-1]+1:run.append(value)
                else:
                    if len(run)>1:runs.append(tuple(run))
                    run=[value]
            if len(run)>1:runs.append(tuple(run))
            self.runs.extend((d.date,d.kind,run) for run in runs)
            previous=self.all_draws[start+i-1] if start+i else None
            repeated=tuple(sorted(set(ns)&set(previous.numbers))) if previous else None
            if repeated is not None:
                count=min(4,len(repeated));self.repeat_counts[count]+=1;self.repeat_last[count]=i
                self.repeat_numbers.update(repeated);self.comparisons+=1
            ending_groups=defaultdict(list)
            for value in ns:ending_groups[value%10].append(value)
            for digit,group in ending_groups.items():
                self.ending_hits[digit]+=len(group);self.ending_draws[digit]+=1
                self.ending_multiple[digit]+=len(group)>=2
                for size in range(2,len(group)+1):
                    for combo in combinations(group,size):self.ending_combos[combo]+=1;self.ending_last[combo]=i
            even=sum(n%2==0 for n in ns);low=sum(n<=22 for n in ns)
            self.details.append({'date':d.date,'kind':d.kind,'numbers':ns,'sum':sum(ns),'mean':mean(ns),
                'min':ns[0],'max':ns[-1],'span':ns[-1]-ns[0],'even':even,'odd':6-even,'low':low,'high':6-low,
                'neighbors':tuple(neighbors),'neighbor_count':len(neighbors),'repeat':repeated,
                'repeat_count':len(repeated) if repeated is not None else None,
                'gaps':tuple(gaps),'gap_min':min(gaps),'gap_max':max(gaps),'gap_mean':mean(gaps),
                'run_max':max(map(len,runs),default=1)})
        self.expected=self.n*6/45;self.sigma=math.sqrt(self.n*(6/45)*(1-6/45))
        self.numbers=[]
        for number,indices in self.hits.items():
            gaps=[b-a for a,b in zip(indices,indices[1:])];count=len(indices)
            delta=count-self.expected
            self.numbers.append({'number':number,'count':count,'percent':pct(count,self.n),
                'last':self.draws[indices[-1]].date if indices else None,
                'pause':self.n-1-indices[-1] if indices else self.n,'unseen':not indices,
                'gap_mean':mean(gaps),'gap_min':min(gaps,default=None),'gap_max':max(gaps,default=None),
                'historic_pause':max((gap-1 for gap in gaps),default=None),'bonus':self.bonus[number],
                'expected':self.expected,'delta':delta,'absolute_delta':abs(delta),
                'relative_delta':pct(delta,self.expected),'sigma':self.sigma,
                'z':delta/self.sigma if self.sigma else None})

    def last_date(self,index):return self.draws[index].date if index is not None else None

    def distribution(self,key):
        counts=Counter(d[key] for d in self.details);last={d[key]:d['date'] for d in self.details}
        return [(f'{n} / {6-n}',counts[n],pct(counts[n],self.n),last.get(n)) for n in range(7)]

    def combination_rows(self,size):
        counts,last=(self.pairs,self.pair_last) if size==2 else (self.triples,self.triple_last)
        rows=[(group,counts[group],pct(counts[group],self.n),self.last_date(last.get(group)),
               self.n-1-last[group] if group in last else None) for group in combinations(range(1,46),size)]
        return sorted(rows,key=lambda row:(-row[1],row[0]))

    def report(self,kind):
        """Alle Zeilen bereitstellen; erst die Oberfläche beschränkt die Seitengröße."""
        if kind not in KINDS:raise ValueError('L002: Unbekannte Statistik')
        tables=[];metrics=[]
        def add(title,columns,rows,filter_column=None):
            tables.append(Table('s_'+title,columns,list(rows),filter_column))
        def cols(*items):return [('s_'+name,fmt) for name,fmt in items]
        combo_cols=cols(('combination','numbers'),('hits','int'),('share_draws','percent'),('last','date'),('since','int'))
        distribution_cols=cols(('distribution','text'),('draw_count','int'),('share_draws','percent'),('last','date'))
        if kind=='overview':
            metrics=[('s_draw_count',self.n,'int'),('s_first',self.draws[0].date if self.n else None,'date'),
                     ('s_last',self.draws[-1].date if self.n else None,'date'),
                     ('s_last_numbers',self.draws[-1].numbers if self.n else None,'numbers')]
            for title,op in (('most',max),('least',min)):
                best=op((r['count'] for r in self.numbers),default=0)
                metrics.append(('s_'+title,tuple(r['number'] for r in self.numbers if r['count']==best) if self.n else None,'numbers'))
                metrics.append(('s_'+title+'_hits',best if self.n else None,'int'))
            add('overview',cols(('number','number'),('hits','int'),('share_draws','percent'),('pause','pause')),
                [(r['number'],r['count'],r['percent'],(r['pause'],r['unseen'])) for r in sorted(self.numbers,key=lambda r:(-r['count'],r['number']))])
        elif kind=='numbers':
            add('numbers',cols(('number','number'),('hits','int'),('share_draws','percent'),('last','date'),('pause','pause'),
                ('gap_mean','float'),('gap_min','int'),('gap_max','int'),('historic_pause','int'),('bonus','int')),
                [(r['number'],r['count'],r['percent'],r['last'],(r['pause'],r['unseen']),r['gap_mean'],r['gap_min'],r['gap_max'],r['historic_pause'],r['bonus']) for r in self.numbers])
        elif kind=='expectation':
            add('expectation',cols(('number','number'),('actual','int'),('expected','float'),('delta','signed'),('absolute_delta','float'),
                ('relative_delta','percent'),('sigma','float'),('z','float')),
                [(r['number'],r['count'],r['expected'],r['delta'],r['absolute_delta'],r['relative_delta'],r['sigma'],r['z']) for r in self.numbers])
        elif kind=='periods':
            windows=[self.all_draws[-n:] for n in WINDOWS]+[self.all_draws]
            counts=[Counter(n for d in draws for n in d.numbers) for draws in windows]
            add('periods',cols(('number','number'))+[(str(n),'int') for n in WINDOWS]+[('s_all','int')],
                [(number,*(c[number] for c in counts)) for number in range(1,46)])
            metrics=[('s_available_'+str(n),len(draws),'int') for n,draws in zip(WINDOWS,windows)]
        elif kind=='draws':
            common=cols(('date','date'),('kind','kind'),('main_numbers','numbers'))
            for name,fields in [('draw_values',(('sum','int'),('mean','float'),('min','number'),('max','number'),('span','int'))),
                ('draw_patterns',(('even','int'),('odd','int'),('low','int'),('high','int'),('neighbor_count','int'),('neighbors','groups'),('repeat_count','int'),('repeat','numbers'))),
                ('draw_gaps',(('gaps','gaps'),('gap_min','int'),('gap_max','int'),('gap_mean','float')))]:
                add(name,common+cols(*fields),[(d['date'],d['kind'],d['numbers'],*(d[key] for key,_ in fields)) for d in reversed(self.details)])
        elif kind=='ranges':
            rows=[]
            for lo,hi in RANGES:
                counts=[sum(lo<=n<=hi for n in d.numbers) for d in self.draws]
                rows.append((f'{lo:02d}–{hi:02d}',sum(counts),pct(sum(counts),6*self.n),mean(counts),counts.count(0),sum(n>=2 for n in counts)))
            add('ranges',cols(('range','text'),('hits','int'),('share_numbers','percent'),('per_draw','float'),('without','int'),('multiple','int')),rows)
        elif kind in ('parity','low_high'):
            add(kind,distribution_cols,self.distribution('even' if kind=='parity' else 'low'))
        elif kind in ('rolling','zscore'):
            width=min(20,self.n)
            values=[]
            for i in range(self.n):
                window=self.draws[max(0,i-width+1):i+1];size=len(window)
                count=sum(number in draw.numbers for draw in window)
                values.append(100*count/size if kind=='rolling' else (count-size*6/45)/math.sqrt(size*(6/45)*(1-6/45)))
            result.update(type='line',labels=[d.date for d in self.draws],values=values,reference=[100*6/45 if kind=='rolling' else 0]*self.n,
                          x_title='s_draw_order',y_title='s_share_draws' if kind=='rolling' else 's_zscore')
        elif kind=='sums':
            values=[d['sum'] for d in self.details];counts=Counter(sum_bin(n) for n in values)
            metrics=[('s_min',min(values,default=None),'int'),('s_max',max(values,default=None),'int'),
                     ('s_mean',mean(values),'float'),('s_median',stdstats.median(values) if values else None,'float')]
            add('sums',cols(('sum_range','text'),('draw_count','int'),('share_draws','percent')),
                [(label,counts[i],pct(counts[i],self.n)) for i,label in enumerate(SUM_BINS)])
        elif kind in ('pairs','triples'):
            add(kind,combo_cols,self.combination_rows(2 if kind=='pairs' else 3),0)
        elif kind=='neighbors':
            one=sum(d['neighbor_count']>=1 for d in self.details);two=sum(d['neighbor_count']>=2 for d in self.details)
            longest=max((d['run_max'] for d in self.details),default=0)
            metrics=[('s_neighbor_one',one,'int'),('s_neighbor_share',pct(one,self.n),'percent'),
                     ('s_neighbor_two',two,'int'),('s_longest_run',longest if self.n else None,'int')]
            for size in (2,3):
                rows=[r for r in self.combination_rows(size) if r[0][-1]-r[0][0]==size-1]
                add('neighbor_pairs' if size==2 else 'neighbor_triples',combo_cols,rows,0)
            add('runs',cols(('date','date'),('kind','kind'),('sequence','numbers'),('length','int')),
                [(date,kind,run,len(run)) for date,kind,run in reversed(self.runs)])
            add('longest_runs',cols(('date','date'),('kind','kind'),('sequence','numbers'),('length','int')),
                [(date,kind,run,len(run)) for date,kind,run in reversed(self.runs) if len(run)==longest])
        elif kind=='repeats':
            metrics=[('s_comparisons',self.comparisons,'int')]
            add('repeats',distribution_cols,[(str(n) if n<4 else '≥4',self.repeat_counts[n],pct(self.repeat_counts[n],self.comparisons),self.last_date(self.repeat_last.get(n))) for n in range(5)])
            add('repeat_numbers',cols(('number','number'),('repeat_count','int')),
                sorted([(n,self.repeat_numbers[n]) for n in range(1,46)],key=lambda row:(-row[1],row[0])))
        elif kind=='endings':
            add('endings',cols(('ending','int'),('hits','int'),('share_numbers','percent'),('with_digit','int'),('multiple','int')),
                [(n,self.ending_hits[n],pct(self.ending_hits[n],6*self.n),self.ending_draws[n],self.ending_multiple[n]) for n in range(10)])
            combos=[group for digit in range(10) for size in range(2,6) for group in combinations([n for n in range(1,46) if n%10==digit],size)]
            add('ending_combos',combo_cols,sorted([(c,self.ending_combos[c],pct(self.ending_combos[c],self.n),self.last_date(self.ending_last.get(c)),
                self.n-1-self.ending_last[c] if c in self.ending_last else None) for c in combos],key=lambda row:(-row[1],row[0])),0)
        elif kind=='gaps':
            count=sum(self.gaps.values())
            metrics=[('s_gap_min',min(self.gaps,default=None),'int'),('s_gap_max',max(self.gaps,default=None),'int'),
                     ('s_gap_mean',sum(g*c for g,c in self.gaps.items())/count if count else None,'float')]
            add('gaps',cols(('gap','int'),('hits','int'),('share_gaps','percent'),('last','date')),
                [(gap,self.gaps[gap],pct(self.gaps[gap],count),self.last_date(self.gap_last.get(gap))) for gap in range(1,45)])
        elif kind=='rankings':
            for title,key,reverse in [('most','count',True),('least','count',False),('long_pause','pause',True),
                    ('short_pause','pause',False),('historic_pause','historic_pause',True),('positive','delta',True),('negative','delta',False)]:
                valid=[r for r in self.numbers if r[key] is not None];missing=[r for r in self.numbers if r[key] is None]
                ordered=sorted(valid,key=lambda r:((-r[key] if reverse else r[key]),r['number']))+missing
                score_format='pause' if key=='pause' else 'signed' if key=='delta' else 'int'
                rows=self.ranked([(r['number'],(r[key],r['unseen']) if key=='pause' else r[key]) for r in ordered])
                add(title,cols(('rank','int'),('number','number'),('score',score_format)),rows)
            for title,size,adjacent in [('pair_ranking',2,False),('triple_ranking',3,False),('neighbor_ranking',2,True)]:
                rows=self.combination_rows(size)
                if adjacent:rows=[r for r in rows if r[0][1]==r[0][0]+1]
                add(title,cols(('rank','int'),('combination','numbers'),('hits','int')),self.ranked([(r[0],r[1]) for r in rows]),1)
        return {'kind':kind,'count':self.n,'available':len(self.all_draws),
                'first':self.draws[0].date if self.n else None,'last':self.draws[-1].date if self.n else None,
                'metrics':metrics,'tables':tables}

    @staticmethod
    def ranked(rows):
        result=[];last=object();rank=0
        for i,(item,score) in enumerate(rows,1):
            if score!=last:rank=i
            result.append((rank,item,score));last=score
        return result

    def chart(self,kind,number=1):
        if kind not in CHARTS or type(number) is not int or not 1<=number<=45:raise ValueError('L002: Ungültige Diagrammauswahl')
        result={'kind':kind,'count':self.n,'number':number,'type':'bar','labels':[],'values':[],
                'x_title':'s_number','y_title':'s_hits'}
        if kind in ('frequency','pause'):
            result['labels']=[f'{n:02d}' for n in range(1,46)]
            result['values']=[r['count'] if kind=='frequency' else r['pause'] for r in self.numbers]
            result['lower_bounds']=[r['unseen'] for r in self.numbers] if kind=='pause' else []
            if kind=='pause':result['y_title']='s_pause'
        elif kind in ('timeline','deviation'):
            count=0;values=[];reference=[]
            for i,d in enumerate(self.draws,1):
                count+=number in d.numbers
                values.append(100*count/i if kind=='timeline' else count-i*6/45)
                reference.append(100*6/45 if kind=='timeline' else 0)
            result.update(type='line',labels=[d.date for d in self.draws],values=values,reference=reference,
                          x_title='s_draw_order',y_title='s_share_draws' if kind=='timeline' else 's_delta')
        elif kind in ('rolling','zscore'):
            width=min(20,self.n)
            values=[]
            for i in range(self.n):
                window=self.draws[max(0,i-width+1):i+1];size=len(window)
                count=sum(number in draw.numbers for draw in window)
                values.append(100*count/size if kind=='rolling' else (count-size*6/45)/math.sqrt(size*(6/45)*(1-6/45)))
            result.update(type='line',labels=[d.date for d in self.draws],values=values,reference=[100*6/45 if kind=='rolling' else 0]*self.n,
                          x_title='s_draw_order',y_title='s_share_draws' if kind=='rolling' else 's_zscore')
        elif kind=='sums':
            counts=Counter(sum_bin(d['sum']) for d in self.details)
            result.update(labels=list(SUM_BINS),values=[counts[i] for i in range(7)],x_title='s_sum_range',y_title='s_draw_count')
        elif kind in ('parity','low_high'):
            rows=self.distribution('even' if kind=='parity' else 'low')
            result.update(labels=[r[0] for r in rows],values=[r[1] for r in rows],x_title='s_'+kind,y_title='s_draw_count')
        else:
            result.update(type='heatmap',labels=[f'{n:02d}' for n in range(1,46)],
                matrix=[[None if a==b else self.pairs[tuple(sorted((a,b)))] for b in range(1,46)] for a in range(1,46)],
                x_title='s_number',y_title='s_number')
        return result
