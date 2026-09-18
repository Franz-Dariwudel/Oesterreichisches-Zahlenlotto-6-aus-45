"""Joker deskriptiv auswerten: Ziffern und Stellen behalten ihre Reihenfolge."""
from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3
from .statistics import Table,pct


def load_joker(path,cancel=None):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        if cancel:con.set_progress_handler(lambda:int(cancel.is_set()),1000)
        con.execute('BEGIN')
        return list(con.execute('SELECT id,datum,kennung,nummer FROM joker_ziehungen ORDER BY datum,id'))


class JokerAnalysis:
    """Nur gezogene Nummern auswerten; führende Nullen bleiben als Text erhalten."""
    def __init__(self,draws,limit=0,cancel=None):
        self.all_draws=sorted(draws,key=lambda r:(r[1],r[0]));self.draws=self.all_draws[-limit:] if limit else self.all_draws[:]
        self.n=len(self.draws);self.positions=Counter();self.hits=Counter();self.last={};self.with_digit=Counter()
        self.counts=Counter();self.number_last={};self.suffixes={size:Counter() for size in (1,2,3)};self.suffix_last={}
        for i,(_,date,kind,number) in enumerate(self.draws):
            if cancel and cancel.is_set():raise InterruptedError('Statistik abgebrochen')
            self.counts[number]+=1;self.number_last[number]=i
            for position,digit in enumerate(number,1):
                self.positions[position,int(digit)]+=1;self.hits[int(digit)]+=1;self.last[position,int(digit)]=i
            self.with_digit.update(map(int,set(number)))
            for size in self.suffixes:
                suffix=number[-size:];self.suffixes[size][suffix]+=1;self.suffix_last[size,suffix]=i

    def report(self,kind='joker'):
        def last(index):return self.draws[index][1] if index is not None else None
        tables=[Table('j_digits',[('j_digit','int'),('s_hits','int'),('j_share_digits','percent'),('j_with_digit','int')],
                      [(digit,self.hits[digit],pct(self.hits[digit],6*self.n),self.with_digit[digit]) for digit in range(10)]),
                Table('j_positions',[('j_position','int'),('j_digit','int'),('s_hits','int'),('s_share_draws','percent'),('s_last','date')],
                      [(position,digit,self.positions[position,digit],pct(self.positions[position,digit],self.n),last(self.last.get((position,digit)))) for position in range(1,7) for digit in range(10)])]
        for size in (1,2,3):
            rows=[]
            for n in range(10**size):
                value=f'{n:0{size}d}';index=self.suffix_last.get((size,value))
                rows.append((value,self.suffixes[size][value],pct(self.suffixes[size][value],self.n),last(index),self.n-1-index if index is not None else None))
            tables.append(Table('j_suffix_'+str(size),[('j_suffix','text'),('s_hits','int'),('s_share_draws','percent'),('s_last','date'),('s_since','int')],sorted(rows,key=lambda r:(-r[1],r[0]))))
        tables.append(Table('j_numbers',[('j_number','text'),('s_hits','int'),('s_last','date')],
                            [(number,count,last(self.number_last[number])) for number,count in sorted(self.counts.items(),key=lambda r:(-r[1],r[0]))]))
        tables.append(Table('j_draws',[('s_date','date'),('s_kind','kind'),('j_number','text'),('j_digit_sum','int'),('j_different','int')],
                            [(date,kind,number,sum(map(int,number)),len(set(number))) for _,date,kind,number in reversed(self.draws)]))
        tables.append(Table('j_periods',[('j_digit','int')]+[(str(n),'int') for n in (10,20,50,100,500)]+[('s_all','int')],
                            [(digit,*(sum(number.count(str(digit)) for _,_,_,number in self.all_draws[-limit:]) for limit in (10,20,50,100,500)),sum(number.count(str(digit)) for _,_,_,number in self.all_draws)) for digit in range(10)]))
        return {'kind':'joker','count':self.n,'available':len(self.all_draws),'first':self.draws[0][1] if self.n else None,
                'last':self.draws[-1][1] if self.n else None,
                'metrics':[('j_latest',self.draws[-1][3] if self.n else None,'text'),('j_distinct_numbers',len(self.counts),'int')], 'tables':tables}
