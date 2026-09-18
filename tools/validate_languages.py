"""Vollständigkeit, Formatfelder, Menühilfe und lokale Links prüfen."""
from pathlib import Path
import json,string,re
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
CODES=['de','en','es','fr','pt','zh','hi','ar','ru','tr']
class Check(HTMLParser):
 def __init__(self):super().__init__();self.ids=[];self.links=[];self.lang=None;self.menus=[];self.text=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='html':self.lang=a.get('lang')
  if 'id' in a:self.ids.append(a['id'])
  if 'data-menu' in a:self.menus.append(a['data-menu'])
  if tag=='a':self.links.append(a.get('href',''))
 def handle_data(self,text):self.text.append(text)
def fields(s):return sorted((name,spec,conv) for _,name,spec,conv in string.Formatter().parse(s) if name is not None)
base=json.loads((ROOT/'languages/en.json').read_text())
expected=json.loads((ROOT/'resources/menu-help-index.json').read_text())['entries']
for code in CODES:
 catalog=json.loads((ROOT/'languages'/f'{code}.json').read_text())
 assert set(catalog)==set(base),(code,'keys')
 for key,value in catalog.items():
  assert isinstance(value,str) and value.strip(),(code,key,'empty')
  assert fields(value)==fields(base[key]),(code,key,'placeholders',value)
  assert not re.search(r'ZXQ|⟦\d{4}⟧',value),(code,key,'translation marker')
 p=Check();p.feed((ROOT/'help'/f'{code}.html').read_text())
 assert p.lang==code,(code,'html lang')
 assert sorted(p.menus)==sorted(expected),(code,'menus')
 assert len(set(p.ids))==len(p.ids),(code,'duplicate ids')
 assert all(link[1:] in p.ids for link in p.links if link.startswith('#')),(code,'broken anchor')
 text=' '.join(p.text)
 assert all(f'L{i:03d}' in text for i in range(1,15)),(code,'error codes')
 assert 'start.sh' not in text,(code,'private starter')
 assert not re.search(r'ZXQ|⟦\d{4}⟧',text),(code,'translation marker')
 print(code,len(catalog),'strings;',len(p.menus),'menu sections; links and placeholders OK')
