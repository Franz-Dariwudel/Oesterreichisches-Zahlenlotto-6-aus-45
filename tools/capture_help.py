"""Echte GTK-Ansichten der laufenden Anwendung für die lokale Hilfe rendern."""
import sys,time,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from unittest.mock import patch
from lotto45.app import App,Gtk,GLib,Gdk
import gi
gi.require_version('Graphene','1.0');gi.require_version('Gsk','4.0')
from gi.repository import Graphene,Gsk
from lotto45.database import connect,ingest
from contextlib import closing
root=Path.cwd();out=root/'help/images';out.mkdir(exist_ok=True)
def pump(seconds=.3):
 until=time.monotonic()+seconds
 while time.monotonic()<until:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.01)
def capture(widget,name):
 pump(.4)
 paint=Gtk.WidgetPaintable.new(widget)
 snap=Gtk.Snapshot.new();paint.snapshot(snap,float(widget.get_width()),float(widget.get_height()))
 node=snap.to_node()
 renderer=widget.get_native().get_renderer()
 bounds=Graphene.Rect();bounds.init(0,0,widget.get_width(),widget.get_height())
 texture=renderer.render_texture(node,bounds);texture.save_to_png(str(out/(name+'.png')))
 controls=[]
 def walk(w):
  if not w.get_visible():return
  if isinstance(w,Gtk.DropDown):
   model=w.get_model();options=[model.get_string(i) for i in range(model.get_n_items())] if isinstance(model,Gtk.StringList) else []
   controls.append({'type':'choice','options':options,'selected':w.get_selected(),'hint':w.get_tooltip_text() or ''})
  elif isinstance(w,Gtk.Entry):controls.append({'type':'entry','value':w.get_text(),'hint':w.get_tooltip_text() or w.get_placeholder_text() or ''})
  elif isinstance(w,Gtk.CheckButton):controls.append({'type':'check','label':w.get_label() or (w.get_child().get_label() if isinstance(w.get_child(),Gtk.Label) else ''),'value':w.get_active()})
  elif isinstance(w,Gtk.Button):controls.append({'type':'button','label':w.get_label() or ''})
  child=w.get_first_child()
  while child:walk(child);child=child.get_next_sibling()
 walk(widget);metadata[name]=controls
 print(name,widget.get_width(),widget.get_height(),flush=True)
metadata={}
with tempfile.TemporaryDirectory() as tmp:
 db=Path(tmp)/'example.sqlite3'
 rows=[]
 for i in range(1,25):
  rows += [{'spiel':'lotto','datum':f'2026-08-{i:02}','zahlen':sorted({1,7,12,25,31,40+i%5}),'zusatzzahl':6}, {'spiel':'joker','datum':f'2026-08-{i:02}','nummer':f'{i:06}'}]
 with closing(connect(db)) as con:ingest(con,json.dumps(rows).encode(),'Beispieldaten für die Hilfe',rows)
 with patch('lotto45.settings.load',return_value={'language':'de','max_tips':10000}):app=App(db)
 app.register(None);app.activate();app.window.set_default_size(1280,1000);pump()
 save_patch=patch('lotto45.settings.save');save_patch.start()
 try:
  for game in ('lotto','joker'):
   app.set_game(game);app.home();capture(app.window,'home-'+game)
   app.history();pump(.8);capture(app.window,'history-'+game)
   app.lookup();capture(app.window,'lookup-'+game)
   app.quotes();pump(.8);capture(app.window,'quotes-'+game)
   app.show_tips();capture(app.window,'tips-'+game)
   app.tip_view.mode.set_selected(1);capture(app.window,'tips-filtered-'+game)
   app.tip_view.mode.set_selected(0);app.tip_view.count.set_text('6');app.tip_view.generate()
   pump(1);capture(app.window,'tips-result-'+game)
   app.show_tips(True);capture(app.window,'tip-history-'+game)
   kinds=('overview','numbers','periods','expectation','rankings','pairs','triples','neighbors','draws','ranges','parity','low_high','sums','repeats','endings','gaps','charts','patterns') if game=='lotto' else ('joker','patterns')
   for kind in kinds:
    app.show_statistics(kind);pump(1)
    capture(app.window,'stats-'+game+'-'+kind)
    if kind=='charts':
     from lotto45.statistics import CHARTS
     for i,chart in enumerate(CHARTS):
      app.statistics_view.chart_select.set_selected(i);pump(.3);capture(app.window,'chart-'+chart)
    if kind=='patterns':
     app.statistics_view.pattern_chart();capture(app.window,'pattern-chart-'+game)
  app.preferences();capture(app.preferences_editor['window'],'settings');app.preferences_editor['window'].close()
  with patch('lotto45.archive_download.load_sources',return_value=json.loads((root/'resources/default_sources.json').read_text())):
   app.download_preferences();pump(.8);capture(app.source_dialog,'download');app.source_dialog.close()
  app.status()
  for tab in range(3):app.inventory_tabs.set_current_page(tab);capture(app.window,'inventory-'+str(tab))
  app.issues();capture(app.window,'issues')
  app.import_log();capture(app.window,'import-log')
  from lotto45.services import update_check_report
  def check(path,sources,report_dir,**kwargs):return update_check_report(path,[],Path(tmp)/'reports',**kwargs)
  with patch('lotto45.services.update_check_report',side_effect=check),patch('lotto45.archive_download.load_sources',return_value=[]):
   app.check_data();pump(1);capture(app.window,'check-data')
  for action in ('about','info'):
   getattr(app,action)();pump()
   dialogs=[w for w in Gtk.Window.get_toplevels() if w.get_visible() and w!=app.window]
   if dialogs:capture(dialogs[-1],action);dialogs[-1].close()
 finally:
  save_patch.stop();app.cancel_searches();app.quit()
 (root/'work/manual-controls.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
