"""GTK-4-Archivansicht. Große Tippkataloge werden ausschließlich gezielt abgefragt."""
import logging
import platform
import sqlite3
import threading
import webbrowser
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import os
# Unter X11 ohne vorausgesetztes DRI3 zeichnen. Eine explizite Rendererwahl
# respektieren; die Einstellung gilt ausschließlich für diesen Prozess.
if os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    os.environ.setdefault('GSK_RENDERER','cairo')
    if os.environ['GSK_RENDERER']=='cairo':
        flags=os.environ.get('GDK_DEBUG','').split(',')
        if 'gl-disable' not in flags:flags.append('gl-disable')
        os.environ['GDK_DEBUG']=','.join(filter(None,flags))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gio,GLib,Gdk,GdkPixbuf
from . import VERSION
from .database import connect,has_other_draw_kinds
from .tip_search import parse_search,search_tips
from .draw_search import parse_date_filter,parse_draw_numbers,search_live_draws
from .date_display import format_date,format_log_dates,format_timestamp
from .inventory import read_inventory
from . import settings
from . import archive_download
from . import recovery
from .widgets import entry,FixedTable,ResultArea,watch_errors,date_control

ROOT=settings.ROOT


class App(Gtk.Application):
    def __init__(self,db):
        super().__init__(application_id='eu.dogtruck.lotto45',flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.db=db; self.busy=False; self.lookup_cancel=None;self.history_cancel=None;self.search_timer=0;self.game='lotto'
        self.recovery_cancel=None;self.recovery_thread=None;self.operation_cancel=threading.Event()
        self.connect('shutdown',lambda *_:self.operation_cancel.set())
        self.connect('shutdown',lambda *_:getattr(self,'tip_view',None) and self.tip_view.cancel.set())
        self.connect('shutdown',lambda *_:self.cancel_searches())
        self.connect('shutdown',lambda *_:self.cancel_recovery())
        self.connect('shutdown',lambda *_:self.quotes_view.close() if getattr(self,'quotes_view',None) else None)
        self.config_error=None
        try: self.config=settings.load()
        except Exception as e:
            logging.exception('L004: Einstellungen'); self.config={'language':'de'}
            self.config_error=str(e)
        if self.db is None:
            try:self.db=settings.database_path(self.config)
            except (ValueError,OSError) as error:
                logging.exception('L004: Gespeicherter Datenbankpfad')
                self.config_error=str(error);self.db=ROOT/'data/lotto.sqlite3'
        self.config_error=self.config_error or self.config.pop('recovery_notice',None)
        self.refresh_language()

    def refresh_language(self):
        self.languages=settings.catalogs(); language=self.config.get('language','de')
        if len(self.languages)==1: language=next(iter(self.languages))
        elif language not in self.languages: language='de' if 'de' in self.languages else 'en'
        from . import date_display
        date_display.LANGUAGE=language
        self.config['language']=language
        Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL if language=='ar' else Gtk.TextDirection.LTR)
        self.text={**self.languages.get('en',{}),**self.languages.get(language,{})}

    def t(self,key): return self.text.get(key,key)

    def do_activate(self):
        self.window=Gtk.ApplicationWindow(application=self,title=f'6 aus 45 · {VERSION}')
        self.window.set_default_size(1040,840)
        self.rebuild(); self.window.present()
        if self.config_error:
            self.notice.set_text(self.config_error)

    def action(self,name,callback):
        a=Gio.SimpleAction.new(name,None); a.connect('activate',lambda *_:self.guard(callback)); self.add_action(a)

    def guard(self,callback):
        try: callback()
        except Exception as e:
            logging.exception('L001: Oberfläche'); self.message('L001',str(e)+'\n'+self.t('error_help'))

    def set_game(self,game):
        """Beim Spielwechsel den Menübereich erhalten; Statistikziele je Spiel merken."""
        if game not in ('lotto','joker'):raise ValueError('L002: Unbekanntes Spiel')
        if game==self.game:return
        view=getattr(self,'current_view',None)
        if view=='history':
            # Der ausgeblendete Zahlenfilter bleibt für die Rückkehr zu Lotto erhalten.
            date_text=self.history_controls['entry'].get_text()
            numbers_text=self.history_controls['numbers'].get_text()
            open_view=lambda:self.history(date_text,numbers_text)
        elif view=='statistics':
            kind=self.statistics_view.kind
            pages=getattr(self,'statistics_pages',{})
            target='patterns' if kind=='patterns' else 'joker' if game=='joker' else pages.get('lotto','overview')
            open_view=lambda:self.show_statistics(target)
        else:
            open_view={'quotes':self.quotes,'lookup':self.lookup,
                       'tips':self.show_tips,'tip_history':lambda:self.show_tips(True)}.get(view,self.home)
        self.game=game;self.rebuild(open_view)

    def rebuild(self,open_view=None):
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.window.set_child(outer)
        # Alte Aktionsnamen bleiben für Tastatur-/Integrationstest-Aufrufe erreichbar.
        for name,callback in [('home',self.home),('lookup',self.lookup),('history',self.history),('quotes',self.quotes),('status',self.status),('issues',self.issues)]:
            if not self.lookup_action(name):self.action(name,callback)
        menus=[('file',[('quit',lambda:self.quit())]),('edit',[('settings',self.preferences)]),
               ('help',[('manual',self.help),('about',self.about),('info',self.info),('logs',self.logs)])]
        model=Gio.Menu()
        for title,items in menus:
            submenu=Gio.Menu()
            if title=='statistics':
                def item(menu,kind):
                    name='frequency' if kind=='periods' else 'stats-'+kind.replace('_','-')
                    if not self.lookup_action(name):self.action(name,lambda k=kind:self.show_statistics(k))
                    menu.append(self.t('s_'+kind),'app.'+name)
                if self.game=='joker':item(submenu,'joker')
                else:
                    item(submenu,'overview')
                    for group,kinds in [('number_menu',('numbers','periods','expectation','rankings')),
                                    ('combination_menu',('pairs','triples','neighbors','endings')),
                                    ('draw_menu',('draws','ranges','parity','low_high','sums','repeats','gaps'))]:
                        section=Gio.Menu()
                        for kind in kinds:item(section,kind)
                        submenu.append_submenu(self.t('s_'+group),section)
                    item(submenu,'charts')
            for name,callback in items:
                if not self.lookup_action(name): self.action(name,callback)
                submenu.append(self.t(name.replace('-','_')),'app.'+name)
            model.append_submenu(self.t(title),submenu)
        for game in ('lotto','joker'):
            menu=Gio.Menu()
            for key,callback in [('home',self.home),('history',self.history),('lookup',self.lookup),('quotes',self.quotes),
                                 ('tip_create',lambda:self.show_tips()),('tip_history',lambda:self.show_tips(True)),
                                 ('tip_save',self.save_tips),('tip_print',self.print_tips)]:
                action=game+'-'+key.replace('_','-')
                if not self.lookup_action(action):self.action(action,lambda g=game,cb=callback:self.game_action(g,cb))
                menu.append(self.t(key),'app.'+action)
            stats_menu=Gio.Menu()
            kinds=('joker',) if game=='joker' else ('overview','numbers','periods','expectation','rankings','pairs','triples','neighbors','draws','ranges','parity','low_high','sums','repeats','endings','gaps','charts')
            for kind in (*kinds,'patterns'):
                action=game+'-analysis-'+kind
                if not self.lookup_action(action):self.action(action,lambda g=game,k=kind:self.game_action(g,lambda:self.show_statistics(k)))
                stats_menu.append(self.t('s_'+kind),'app.'+action)
            menu.append_submenu(self.t('statistics'),stats_menu)
            model.insert_submenu(2 if game=='lotto' else 3,self.t('game_'+game),menu)
        shared=Gio.Menu()
        for key,callback in [('check_data',self.check_data),('status',self.status),('issues',self.issues),('archive-download',self.download_preferences),
                             ('import_log',self.import_log),
                             ('db_backup',self.db_backup),('recovery_choose',self.choose_database),
                             ('local_import',self.local_import)]:
            name=key.replace('_','-')
            if not self.lookup_action(name):self.action(name,callback)
            shared.append(self.t(key.replace('-','_')),'app.'+name)
        model.insert_submenu(4,self.t('shared'),shared)
        profile_menu=Gio.Menu()
        for key in ('load','save','delete'):
            name='profile-'+key
            if not self.lookup_action(name):self.action(name,lambda k=key:self.profile_action(k))
            profile_menu.append(self.t('profile_'+key),'app.'+name)
        model.insert_submenu(5,self.t('profile'),profile_menu)
        self.menubar=Gtk.PopoverMenuBar.new_from_model(model)
        outer.append(self.menubar)
        game_row=Gtk.Box(spacing=0,halign=Gtk.Align.START,margin_start=18);self.game_row=game_row
        self.game_buttons={}
        for game in ('lotto','joker'):
            button=Gtk.ToggleButton(label=game.capitalize())
            if self.game_buttons:button.set_group(self.game_buttons['lotto'])
            button.set_active(game==self.game)
            button.connect('toggled',lambda b,g=game:self.guard(lambda:self.set_game(g)) if b.get_active() else None)
            self.game_buttons[game]=button;game_row.append(button)
        outer.append(game_row)
        update=Gtk.Button(label=self.t('check_data'),halign=Gtk.Align.START,margin_start=18)
        update.connect('clicked',lambda *_:self.guard(self.check_data));game_row.append(update)
        # Native Menüleiste: Systemdarstellung und Tastaturbedienung beibehalten.
        def fix_short_menus(*_):
            def fix(widget):
                if isinstance(widget,Gtk.PopoverMenu): widget.add_css_class('compact-menu')
                if isinstance(widget,Gtk.Stack): widget.set_vhomogeneous(False)
                child=widget.get_first_child()
                while child: fix(child);child=child.get_next_sibling()
            item=self.menubar.get_first_child()
            index=0
            while item:
                if index in (0,1):fix(item)
                item=item.get_next_sibling();index+=1
        fix_short_menus();self.menubar.connect('map',fix_short_menus)
        if not hasattr(self,'menu_css'):
            self.menu_css=Gtk.CssProvider()
            self.menu_css.load_from_data(b'.compact-menu scrollbar.vertical, .compact-menu scrollbar.vertical range, .compact-menu scrollbar.vertical trough, .compact-menu scrollbar.vertical slider { min-height: 0; } label.lotto-error { color: @error_color; } .section-panel { border: 1px solid alpha(currentColor, 0.20); border-radius: 6px; padding: 8px; } .section-controls { border-bottom: 1px solid alpha(currentColor, 0.18); padding-bottom: 6px; } .page-content label.heading { border-bottom: 1px solid alpha(currentColor, 0.24); padding-top: 5px; padding-bottom: 4px; }')
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.menu_css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.notice=watch_errors(Gtk.Label(label='',xalign=0,wrap=True))
        self.notice.connect('notify::label',lambda label,*_:label.set_visible(bool(label.get_text())))
        self.notice.set_visible(False)
        self.notice.set_margin_start(18);self.notice.set_margin_end(18);outer.append(self.notice)
        self.page_heading=Gtk.Label(xalign=0);self.page_heading.add_css_class('title-2')
        self.page_heading.set_margin_start(18);self.page_heading.set_margin_top(4);outer.append(self.page_heading)
        outer.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        scroll=Gtk.ScrolledWindow(vexpand=True);self.page_scroll=scroll;outer.append(scroll)
        self.content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.content.add_css_class('page-content')
        for side in ('start','end','top','bottom'): getattr(self.content,'set_margin_'+side)(12 if side in ('start','end') else 6)
        scroll.set_child(self.content); (open_view or self.home)()
        outer.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.statusbar=Gtk.Label(xalign=0,wrap=True,margin_start=18,margin_end=18,margin_bottom=8);outer.append(self.statusbar)
        self.update_statusbar()

    def clear(self,title,pinned=False,game_specific=True,view=None):
        # Eine feste Ansichtskennung verhindert Verwechslungen durch alte Widgets
        # oder übersetzte Überschriften nach einem Menü- oder Spielwechsel.
        self.current_view=view
        if getattr(self,'quotes_view',None):
            self.quotes_view.close();self.quotes_view=None
        if getattr(self,'statistics_view',None):
            self.statistics_view.close();self.statistics_view=None
        self.cancel_searches()
        self.window.set_focus(None)
        while child:=self.content.get_first_child(): self.content.remove(child)
        self.page_heading.set_text(title)
        self.game_row.set_visible(game_specific)
        self.page_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.NEVER if pinned else Gtk.PolicyType.AUTOMATIC)

    def cancel_searches(self):
        """Alte Zeitgeber und Datenbankabfragen dürfen keine neue Ansicht überschreiben."""
        if self.search_timer:GLib.source_remove(self.search_timer);self.search_timer=0
        for attr in ('lookup_cancel','history_cancel'):
            cancel=getattr(self,attr)
            if cancel:cancel.set();setattr(self,attr,None)

    def queue_search(self,callback):
        """Kurze Tipppause bündelt Zeichen; eine vollständige Zahl genügt zur Suche."""
        if self.search_timer:GLib.source_remove(self.search_timer)
        def fire():
            self.search_timer=0;self.guard(callback);return False
        self.search_timer=GLib.timeout_add(200,fire)

    def label(self,text,container=None):
        l=watch_errors(Gtk.Label(label=text,xalign=0,selectable=True,wrap=True))
        (container if container is not None else self.content).append(l);return l

    def entry(self,**kwargs):return entry(self.t,**kwargs)

    def grid(self,headers,rows,container=None):
        table=FixedTable(headers,list(rows),compact=True)
        (container if container is not None else self.content).append(table)
        return table

    def draw_quotes(self,rows,container,spread=False):
        table=FixedTable([self.t('rank'),self.t('winners'),self.t('amount')],rows,[0,1,1],compact=True)
        if spread:table.spread()
        container.append(table)
        return table

    def show_draw(self,con,game,row,container=None,spread_quotes=False,show_quotes=True):
        """Datum/Zahlen zeigen; Gewinntabellen nur für Ansichten mit Quoten laden."""
        container=container if container is not None else self.content
        if not row: self.label(self.t('empty'),container);return
        kind=' · '+row['kennung'] if row['kennung']!='haupt' else ''
        self.label(f"{game.capitalize()} · {format_date(row['datum'])}"+kind,container)
        draw_area=container
        if spread_quotes:
            draw_area=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,halign=Gtk.Align.START)
            container.append(draw_area)
        balls=Gtk.Box(spacing=8)
        if game=='lotto':
            tip=con.execute('SELECT n1,n2,n3,n4,n5,n6 FROM lotto_tipps WHERE id=?',(row['tipp_id'],)).fetchone()
            nums=[('white',n) for n in tip]+[('green',row['zusatzzahl'])]
        else: nums=[('blue',n) for n in row['nummer']]
        for color,n in nums:
            pic=Gtk.Picture.new_for_filename(str(ROOT/'resources'/f'ball-{color}-{n}.svg'));pic.set_size_request(66,70);balls.append(pic)
        draw_area.append(balls)
        if show_quotes:
            qs=list(con.execute(f'SELECT k.code,q.* FROM {game}_quoten q JOIN gewinnklassen k ON k.id=q.klasse_id WHERE ziehung_id=? ORDER BY k.id',(row['id'],)))
            quotes=[]
            for q in qs:
                values,_=self.quote_values(game,row['datum'],q)
                quotes.append(values)
            if quotes:self.draw_quotes(quotes,draw_area,spread_quotes)
            else:self.label(self.t('quotes_missing'),draw_area)

    def quote_values(self,game,date,q):
        """Letzte Ziehung und Quotenarchiv verwenden dieselben Betragsregeln."""
        from .joker_rules import standard_amount
        rank=q['code'];amount=self.quote_amount(q);supplement=False
        if game=='joker':
            if rank.isdigit() and 1<=int(rank)<=6:
                rank=self.t('joker_rank_one' if rank=='6' else 'joker_rank').format(rank=rank,digits=7-int(rank))
            fixed=standard_amount(date,q['code'])
            if q['betrag_hundertstel'] is None and fixed is not None:
                amount=self.money({'betrag_hundertstel':fixed,'waehrung':'EUR'});supplement=True
        winners='—' if q['gewinner'] is None else f"{q['gewinner']:,}"
        if self.config['language']=='de':winners=winners.replace(',','.')
        return [rank,winners,amount],supplement

    def quote_amount(self,q):
        """Jackpots kompakt als JP/2JP/3JP anzeigen; Rohdaten unverändert lassen."""
        from .quotes import jackpot_label
        amount=self.money(q)
        if q['betrag_art']=='jackpot':
            return amount+' · '+jackpot_label(q['status'])
        if q['betrag_art']=='unbekannt' and q['betrag_hundertstel'] is not None:
            amount+=' · '+self.t('unbekannt')
        if q['status']: amount+=' · '+jackpot_label(q['status'])
        return amount

    def money(self,q):
        n=q['betrag_hundertstel']
        if n is None:return '—'
        value=f'{n//100:,}.{n%100:02d}'
        if self.config['language']=='de':value=value.replace(',','_').replace('.',',').replace('_','.')
        return value+' '+q['waehrung']

    def home(self):
        self.clear(self.game.capitalize()+' · '+self.t('home'),view='home')
        try:
            with closing(connect(self.db,create=False)) as con:
                # Fehlende/umbenannte Archive niemals stillschweigend neu erzeugen.
                populated=any(con.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
                              for table in ('lotto_tipps','joker_tipps','lotto_ziehungen','joker_ziehungen'))
                if not populated:
                    logging.warning('L009: Datenbank enthält keine Tipps oder Ziehungen: %s',self.db)
                    self.database_notice('database_empty');return
                row=con.execute(f'SELECT * FROM {self.game}_ziehungen ORDER BY datum DESC,id DESC LIMIT 1').fetchone()
                card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,halign=Gtk.Align.START);card.add_css_class('section-panel');self.content.append(card)
                self.show_draw(con,self.game,row,container=card,spread_quotes=True)
        except (OSError,sqlite3.Error,ValueError):
            logging.exception('L001: Datenbank fehlt oder ist nicht lesbar: %s',self.db)
            self.database_notice('database_missing' if not Path(self.db).exists() else 'database_invalid');return
        self.label(self.t('coverage_note'))

    def database_notice(self,key):
        """Bei Datenverlust Wiederherstellung und Neuaufbau direkt anbieten."""
        self.label(self.t(key)).add_css_class('title-2')
        self.label(self.t('database_path').format(path=Path(self.db).absolute()))
        self.label(self.t('recovery_hint'))
        controls=Gtk.Box(spacing=8);self.content.append(controls)
        for key,callback in [('recovery_choose',self.choose_database),
                             ('recovery_new',lambda:self.download_preferences(rebuild=True)),
                             ('recovery_retry',self.home)]:
            button=Gtk.Button(label=self.t(key));button.connect('clicked',lambda *_,cb=callback:self.guard(cb));controls.append(button)
        found=recovery.candidates(self.db,ROOT/'data')
        if found:
            self.label(self.t('recovery_found')).add_css_class('heading')
            for path in found[:10]:
                row=Gtk.Box(spacing=12);label=self.label(str(path),row);label.set_hexpand(True)
                button=Gtk.Button(label=self.t('recovery_restore'),halign=Gtk.Align.START)
                button.connect('clicked',lambda *_,p=path:self.restore_database(p));row.append(button);self.content.append(row)
        self.recovery_stop=Gtk.Button(label=self.t('recovery_cancel'),halign=Gtk.Align.START)
        self.recovery_stop.set_sensitive(self.recovery_cancel is not None)
        self.recovery_stop.connect('clicked',lambda *_:self.cancel_recovery());self.content.append(self.recovery_stop)

    def choose_database(self):
        if self.busy:self.notice.set_text(self.t('busy'));return
        chooser=Gtk.FileChooserNative(title=self.t('recovery_choose'),transient_for=self.window,
            action=Gtk.FileChooserAction.OPEN,accept_label=self.t('recovery_restore'),cancel_label=self.t('close'))
        file_filter=Gtk.FileFilter();file_filter.set_name(self.t('recovery_database_files'))
        for pattern in ('*.sqlite3','*.sqlite','*.db','*.bak'):file_filter.add_pattern(pattern)
        chooser.add_filter(file_filter)
        all_files=Gtk.FileFilter();all_files.set_name(self.t('recovery_all_files'));all_files.add_pattern('*');chooser.add_filter(all_files)
        folder=Path(self.db).parent
        if folder.is_dir():chooser.set_current_folder(Gio.File.new_for_path(str(folder)))
        def selected(dialog,response):
            file=dialog.get_file() if response==Gtk.ResponseType.ACCEPT else None
            dialog.destroy()
            if file and file.get_path():self.restore_database(Path(file.get_path()))
        chooser.connect('response',selected);self.recovery_chooser=chooser;chooser.show()

    def restore_database(self,source):
        preferred=Path(self.db)
        self.start_recovery(lambda cancel,progress:recovery.restore(source,preferred,cancel,progress))

    def cancel_recovery(self):
        if self.recovery_cancel is not None:
            self.recovery_cancel.set()
            if hasattr(self,'notice'):self.notice.set_text(self.t('recovery_cancelling'))

    def start_recovery(self,job,on_done=None,on_progress=None):
        """Kopieren/Aufbau außerhalb von GTK; die neue Auswahl erst nach Prüfung speichern."""
        if self.busy:self.notice.set_text(self.t('busy'));return False
        self.cancel_searches();cancel=threading.Event();self.recovery_cancel=cancel;self.busy=True
        self.notice.set_text(self.t('recovery_check'))
        if hasattr(self,'recovery_stop'):self.recovery_stop.set_sensitive(True)
        def progress(key,value):
            def show():
                if self.recovery_cancel is not cancel:return False
                text=self.t(key)+(': '+str(value) if value else '')
                self.notice.set_text(text)
                if on_progress:on_progress(text)
                return False
            GLib.idle_add(show)
        def finished(result=None,error=None,cancelled=False):
            if self.recovery_cancel is not cancel:return False
            self.recovery_cancel=None;self.busy=False
            if hasattr(self,'recovery_stop'):self.recovery_stop.set_sensitive(False)
            if cancelled:
                self.notice.set_text(self.t('recovery_cancelled'))
            elif error:
                self.notice.set_text(str(error)+'\n'+self.t('recovery_error_help'))
            else:
                try:
                    config={**self.config,'database':str(result['path'])}
                    settings.save(config)
                except Exception as failure:
                    logging.exception('L010: Wiederhergestellte Datenbank konnte nicht ausgewählt werden: %s',result['path'])
                    error=self.t('recovery_save_error').format(path=result['path'])+'\n'+str(failure)
                    self.notice.set_text(error)
                else:
                    self.config=config;self.db=Path(result['path']);self.home()
                    message=self.t('recovery_done').format(path=self.db)
                    if result['errors']:message+='\n'+self.t('recovery_partial').format(count=len(result['errors']))
                    self.notice.set_text(('✓ ' if not result['errors'] else '')+message)
            if on_done:on_done(result,error,cancelled)
            return False
        def worker():
            try:result=job(cancel,progress)
            except recovery.Cancelled:GLib.idle_add(finished,None,None,True)
            except Exception as error:
                logging.exception('L010: Datenbank-Wiederherstellung')
                GLib.idle_add(finished,None,str(error))
            else:GLib.idle_add(finished,result)
        # Bei normalem Beenden noch Abbruch und Aufräumen zulassen, auch während eines Downloads.
        self.recovery_thread=threading.Thread(target=worker,daemon=False);self.recovery_thread.start()
        return True

    def status(self):
        """Bestand in überschaubaren Reitern ohne Scrollbereiche darstellen."""
        self.clear(self.t('status'),pinned=True,game_specific=False)
        data=read_inventory(self.db)
        def number(n):return f'{n:,}'.replace(',','.') if self.config['language']=='de' else f'{n:,}'
        def size(n):
            value=f'{n/1048576:.2f}'
            return (value.replace('.',',') if self.config['language']=='de' else value)+' MiB'
        date=format_date
        tabs=Gtk.Notebook(vexpand=True)
        self.content.append(tabs)
        def section(title):
            pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            for side in ('start','end','top','bottom'):getattr(pane,'set_margin_'+side)(8)
            tabs.append_page(pane,Gtk.Label(label=title))
            return pane
        overview=section(self.t('inventory_games'))
        archive=section(self.t('inventory_archive'))
        tables=section(self.t('inventory_tables').format(count=len(data['tables'])))
        self.inventory_tabs=tabs
        refresh=Gtk.Button(label=self.t('refresh'),halign=Gtk.Align.START)
        refresh.connect('clicked',lambda *_:self.guard(self.status));overview.append(refresh)
        metrics=Gtk.Box(spacing=32,halign=Gtk.Align.START)
        overview.append(metrics)
        for title,value in [('inventory_size',size(data['sizes']['database'])),
                            ('inventory_total_rows',number(data['total_rows'])),
                            ('inventory_total_draws',number(data['total_draws']))]:
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);box.add_css_class('section-panel')
            self.label(self.t(title),box)
            value_label=self.label(value,box);value_label.add_css_class('title-2');metrics.append(box)
        def table(headers,rows,container=None):
            # Kleine Bestandsübersichten vollständig in einem Raster anzeigen.
            # Nur die gesamte Seite scrollt, nicht einzelne Tabellenabschnitte.
            grid=Gtk.Grid(column_spacing=24,row_spacing=5,halign=Gtk.Align.START)
            grid.add_css_class('section-panel')
            for y,row in enumerate([headers,*rows]):
                for x,value in enumerate(row):
                    label=Gtk.Label(label=str(value),xalign=0 if x==0 else 1,
                                    selectable=True,wrap=True,max_width_chars=42 if x==0 else 24)
                    if y==0:label.add_css_class('heading')
                    grid.attach(label,x,y,1,1)
            (container if container is not None else overview).append(grid)
            return grid
        games=[data['games'][game] for game in ('lotto','joker')]
        rows=[[self.t('inventory_combinations')]+[
            number(game['tips']) if game['tips']==game['possible'] else
            self.t('inventory_stored_of').format(stored=number(game['tips']),possible=number(game['possible']))
            for game in games]]
        for label,key in [
                          ('inventory_draws','draws'),('inventory_first','first'),
                          ('inventory_last','last'),('inventory_quotes','quotes'),
                          ('inventory_missing_amounts','missing_amounts')]:
            rows.append([self.t(label)]+[date(game[key]) if key in ('first','last') else number(game[key]) for game in games])
        rows.insert(1,[self.t('inventory_catalog')]+[
            self.t('inventory_complete') if game['tips']==game['possible'] else self.t('inventory_incomplete').format(count=number(game['possible']-game['tips'])) for game in games])
        table([self.t('inventory_category'),'Lotto','Joker'],rows)
        table([self.t('inventory_category'),self.t('inventory_count')],[
            [self.t(key),number(data['tables'][table])] for key,table in (
                ('inventory_sources','import_quellen'),('issues','import_fehler'),('inventory_changes','aenderungen'))],archive)
        self.label(self.t('inventory_scope'),archive)
        self.label(self.t('inventory_file')+': '+data['path'],archive)
        self.label(self.t('inventory_storage').format(database=number(data['sizes']['database']),
            auxiliary=size(data['sizes']['wal']+data['sizes']['shm'])),archive)
        # Auch kleine Fenster behalten kurze Tabellenseiten ohne innere Scrollleiste.
        table_pages=Gtk.Notebook()
        tables.append(table_pages)
        entries=list(data['tables'].items())
        for start in range(0,len(entries),8):
            pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            table_pages.append_page(pane,Gtk.Label(label=f'{start+1}–{min(start+8,len(entries))}'))
            table([self.t('inventory_table'),self.t('inventory_count')],
                  [[name,number(count)] for name,count in entries[start:start+8]],pane)

    def issues(self):
        self.clear(self.t('issues'),game_specific=False)
        from .import_review import read_reviews
        with closing(connect(self.db,create=False)) as con:
            rows=read_reviews(con)
        self.label(self.t('review_intro'))
        self.label(self.t('review_count').format(count=len(rows)))
        grouped={}
        for row in rows:grouped.setdefault(row['category'],[]).append(row)
        for category,items in grouped.items():
            self.label(self.t('review_'+category+'_title')+f' ({len(items)})').add_css_class('heading')
            self.label(self.t('review_'+category+'_body'))
            details=Gtk.Expander(label=self.t('review_details').format(count=len(items)))
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            for row in items:
                title=f"#{row['id']}"+(' · '+', '.join(format_date(date) for date in row['dates']) if row['dates'] else '')
                self.label(title,box).add_css_class('heading')
                self.label(self.t('review_source').format(source=row['uri'],line=row['zeile'] if row['zeile'] is not None else '—'),box)
                self.label(self.t('review_original').format(message=row['meldung'],raw=row['roh']),box)
            details.set_child(box);self.content.append(details)

    def quotes(self):
        from .quotes_ui import QuotesView
        self.clear(self.game.capitalize()+' · '+self.t('quotes'),pinned=True,view='quotes')
        self.quotes_view=QuotesView(self)

    def history(self,date_text='',numbers_text=''):
        """Zeitraum und optionale Lotto-Zahlen gemeinsam filtern, Details seitenweise zeigen."""
        self.clear(self.game.capitalize()+' · '+self.t('history'),pinned=True,view='history'); self.label(self.t('history_hint'))
        inputs=Gtk.Box(spacing=8);inputs.add_css_class('section-controls');self.content.append(inputs)
        entry=self.entry(placeholder_text='TT.MM.JJJJ',width_chars=10);inputs.append(date_control(entry,self.t))
        button=Gtk.Button(label=self.t('search'));inputs.append(button)
        extras=Gtk.Box(spacing=8);self.content.append(extras)
        weekday=Gtk.DropDown.new_from_strings([self.t('s_all'),'Mo','Di','Mi','Do','Fr','Sa','So']);extras.append(weekday)
        kind_entry=self.entry(placeholder_text=self.t('tip_kind'));extras.append(kind_entry)
        kind_entry.set_visible(has_other_draw_kinds(self.db,self.game))
        numbers_row=Gtk.Box(spacing=8);self.content.append(numbers_row)
        numbers_row.append(Gtk.Label(label=self.t('history_numbers'),xalign=0))
        numbers_entry=self.entry(placeholder_text='07 23',hexpand=True);numbers_row.append(numbers_entry)
        entry.set_text(date_text);numbers_entry.set_text(numbers_text)
        numbers_hint=self.label(self.t('history_numbers_hint'))
        numbers_row.set_visible(self.game=='lotto');numbers_hint.set_visible(self.game=='lotto')
        status=self.label('');navigation=Gtk.Box(spacing=8);navigation.add_css_class('section-controls');self.content.append(navigation)
        first=Gtk.Button(label=self.t('first_page'));previous=Gtk.Button(label=self.t('previous_page'))
        next_button=Gtk.Button(label=self.t('next_page'));last=Gtk.Button(label=self.t('last_page'))
        page_label=Gtk.Label(label='');page_entry=self.entry(width_chars=5,max_width_chars=5)
        page_entry.set_tooltip_text(self.t('page_number'));go=Gtk.Button(label=self.t('go_page'))
        for widget in (first,previous,page_label,page_entry,go,next_button,last):navigation.append(widget)
        navigation.set_sensitive(False)
        scroll=ResultArea();self.content.append(scroll)
        state={'rows':[],'page':0,'pages':0,'period':None,'numbers':(),'normalizing':False}

        def reset(*_):
            self.cancel_searches()
            state.update(rows=[],page=0,pages=0,period=None,numbers=())
            status.set_text('');page_label.set_text('');page_entry.set_text('')
            navigation.set_sensitive(False);button.set_sensitive(True);scroll.set_child(None)

        def display(page):
            page=max(0,min(page,state['pages']-1));rows=state['rows'];total=len(rows)
            # Nur zehn Ziehungen mit Kugeln zugleich erzeugen. Alle Treffer bleiben erreichbar.
            listing=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            with closing(sqlite3.connect(Path(self.db).resolve().as_uri()+'?mode=ro',uri=True,timeout=60)) as con:
                con.row_factory=sqlite3.Row
                for row in rows[page*10:(page+1)*10]:self.show_draw(con,row['spiel'],row,listing,show_quotes=False)
            scroll.set_child(listing);scroll.get_vadjustment().set_value(0);state['page']=page
            result_key='history_filtered_results' if state['numbers'] else 'history_game_results'
            status.set_text('✓ '+self.t(result_key).format(
                period=state['period'].label or self.t('s_all'),total=total,lotto=sum(row['spiel']=='lotto' for row in rows),
                joker=sum(row['spiel']=='joker' for row in rows),game=self.game.capitalize(),first=page*10+1,last=min((page+1)*10,total),
                numbers=' '.join(f'{n:02d}' for n in state['numbers'])))
            page_label.set_text(self.t('lookup_page').format(page=page+1,pages=state['pages']))
            page_entry.set_text(str(page+1));navigation.set_sensitive(True)
            first.set_sensitive(page>0);previous.set_sensitive(page>0)
            next_button.set_sensitive(page+1<state['pages']);last.set_sensitive(page+1<state['pages'])

        def search(normalize=False):
            reset()
            number_text=numbers_entry.get_text() if self.game=='lotto' else ''
            if not entry.get_text().strip() and not number_text.strip() and weekday.get_selected()==0 and not kind_entry.get_text().strip():return
            try:period=parse_date_filter(entry.get_text())
            except ValueError:
                status.set_text(self.t('history_invalid'));return
            try:numbers=parse_draw_numbers(number_text)
            except ValueError:
                status.set_text(self.t('history_numbers_invalid'));return
            if normalize and self.game=='lotto':
                state['normalizing']=True
                numbers_entry.set_text(' '.join(f'{n:02d}' for n in numbers));state['normalizing']=False
            weekday_value=weekday.get_selected()-1;kind_value=kind_entry.get_text().strip()
            cancel=threading.Event();self.history_cancel=cancel;game=self.game
            status.set_text(self.t('busy'));button.set_sensitive(False)

            def complete(rows=None,error=None):
                if cancel.is_set() or self.history_cancel is not cancel:return False
                self.history_cancel=None;button.set_sensitive(True)
                if error:status.set_text('L001: '+error+'\n'+self.t('error_help'));return False
                def show():
                    state.update(rows=rows,period=period,pages=(len(rows)+9)//10,numbers=numbers)
                    if rows:display(0)
                    else:
                        empty_key='history_filtered_empty' if numbers else 'history_empty'
                        status.set_text(self.t(empty_key).format(period=period.label or self.t('s_all'),numbers=' '.join(f'{n:02d}' for n in numbers)))
                guarded(show);return False

            def worker():
                try:
                    with closing(sqlite3.connect(Path(self.db).resolve().as_uri()+'?mode=ro',uri=True,timeout=60)) as con:
                        con.set_progress_handler(lambda:int(cancel.is_set()),1000);con.execute('BEGIN')
                        rows=search_live_draws(con,period,numbers,game=game)
                        from datetime import date
                        rows=[r for r in rows if (weekday_value==-1 or date.fromisoformat(r['datum']).weekday()==weekday_value) and (not kind_value or r['kennung']==kind_value)]
                    GLib.idle_add(complete,rows)
                except Exception as error:
                    if not cancel.is_set():
                        logging.exception('L001: Datumssuche');GLib.idle_add(complete,None,str(error))
            threading.Thread(target=worker,daemon=True).start()

        def jump():
            try:
                page=int(page_entry.get_text())
                if not 1<=page<=state['pages']:raise ValueError()
            except ValueError:
                status.set_text(self.t('lookup_invalid_page').format(pages=state['pages']));return
            display(page-1)

        def guarded(callback):
            try:callback()
            except Exception as error:
                logging.exception('L001: Datumssuche');reset()
                status.set_text('L001: '+str(error)+'\n'+self.t('error_help'))

        def changed(*_):
            if state['normalizing']:return
            reset()
            if entry.get_text().strip() or weekday.get_selected()!=0 or kind_entry.get_text().strip() or (self.game=='lotto' and numbers_entry.get_text().strip()):
                self.queue_search(lambda:guarded(search))
        weekday.connect('notify::selected',changed);kind_entry.connect('changed',changed)
        entry.connect('changed',changed);entry.connect('activate',lambda *_:guarded(lambda:search(True)))
        numbers_entry.connect('changed',changed);numbers_entry.connect('activate',lambda *_:guarded(lambda:search(True)))
        button.connect('clicked',lambda *_:guarded(lambda:search(True)))
        first.connect('clicked',lambda *_:guarded(lambda:display(0)))
        previous.connect('clicked',lambda *_:guarded(lambda:display(state['page']-1)))
        next_button.connect('clicked',lambda *_:guarded(lambda:display(state['page']+1)))
        last.connect('clicked',lambda *_:guarded(lambda:display(state['pages']-1)))
        go.connect('clicked',lambda *_:guarded(jump));page_entry.connect('activate',lambda *_:guarded(jump))
        self.history_controls={'kind':kind_entry,'entry':entry,'numbers':numbers_entry,'search':button,'status':status,'state':state,'scroll':scroll,
                               'first':first,'previous':previous,'next':next_button,'last':last,
                               'page':page_entry,'go':go,'page_label':page_label}
        changed()
        entry.grab_focus()

    def lookup(self):
        """Nur tatsächlich gezogene Zahlenkombinationen mit allen Ziehungsdaten zeigen."""
        self.clear(self.game.capitalize()+' · '+self.t('lookup'),pinned=True,view='lookup');self.label(self.t('lookup_hint_'+self.game))
        inputs=Gtk.Box(spacing=8);inputs.add_css_class('section-controls');self.content.append(inputs)
        entry=self.entry(hexpand=True,placeholder_text='001234' if self.game=='joker' else '07 / 07 23 / 01 02 03 04 05 06');inputs.append(entry)
        button=Gtk.Button(label=self.t('search'));inputs.append(button)
        result=self.label('')
        navigation=Gtk.Box(spacing=8);navigation.add_css_class('section-controls');self.content.append(navigation)
        first=Gtk.Button(label=self.t('first_page'));previous=Gtk.Button(label=self.t('previous_page'))
        next_button=Gtk.Button(label=self.t('next_page'));last=Gtk.Button(label=self.t('last_page'))
        page_label=Gtk.Label(label='');page_entry=self.entry(width_chars=7,max_width_chars=7)
        page_entry.set_tooltip_text(self.t('page_number'))
        go=Gtk.Button(label=self.t('go_page'))
        for widget in (first,previous,page_label,page_entry,go,next_button,last):navigation.append(widget)
        navigation.set_sensitive(False)
        scroll=ResultArea();self.content.append(scroll)
        state={'result':None,'normalizing':False}

        def reset(*_):
            self.cancel_searches()
            state['result']=None;result.set_text('');page_label.set_text('');page_entry.set_text('')
            navigation.set_sensitive(False);button.set_sensitive(True);scroll.set_child(None)

        def number(value):
            return f'{value:,}'.replace(',','.') if self.config['language']=='de' else f'{value:,}'

        def load(page=0,normalize=False):
            reset()
            if not entry.get_text().strip():return
            try:query=parse_search(entry.get_text(),game=self.game)
            except ValueError:
                result.set_text(self.t('lookup_invalid_'+self.game));return
            if normalize and query.game=='lotto':
                state['normalizing']=True
                entry.set_text(' '.join(f'{n:02d}' for n in query.numbers));state['normalizing']=False
            cancel=threading.Event();self.lookup_cancel=cancel
            result.set_text(self.t('busy'));button.set_sensitive(False)

            def complete(data=None,error=None):
                # Geänderte Eingaben oder ein Ansichtswechsel verwerfen alte Ergebnisse.
                if cancel.is_set() or self.lookup_cancel is not cancel:return False
                self.lookup_cancel=None;button.set_sensitive(True)
                if error:
                    result.set_text('L001: '+error+'\n'+self.t('error_help'));return False
                state['result']=data
                message=self.t('lookup_results').format(**{k:number(data[k]) for k in ('total','first','last')})
                result.set_text('✓ '+message)
                page_label.set_text(self.t('lookup_page').format(page=number(data['page']+1),pages=number(data['pages'])))
                page_entry.set_text(str(data['page']+1));navigation.set_sensitive(bool(data['total']))
                first.set_sensitive(data['page']>0);previous.set_sensitive(data['page']>0)
                next_button.set_sensitive(data['page']+1<data['pages']);last.set_sensitive(data['page']+1<data['pages'])
                rows=[]
                for row in data['rows']:
                    tip=row['tip'] if isinstance(row['tip'],str) else '  '.join(f'{n:02d}' for n in row['tip'])
                    dates=', '.join(format_date(date) for date in row['dates']) if row['dates'] else self.t('not_drawn')
                    rows.append([tip,dates])
                scroll.set_child(FixedTable([self.t('combination'),self.t('draw_dates')],rows))
                return False

            def worker():
                try:
                    with closing(sqlite3.connect(Path(self.db).resolve().as_uri()+'?mode=ro',uri=True,timeout=60)) as con:
                        con.set_progress_handler(lambda:int(cancel.is_set()),10000)
                        con.execute('BEGIN')
                        data=search_tips(con,query,page)
                    GLib.idle_add(complete,data)
                except Exception as error:
                    if not cancel.is_set():
                        logging.exception('L001: Tipp-Suche');GLib.idle_add(complete,None,str(error))
            threading.Thread(target=worker,daemon=True).start()

        def jump():
            data=state['result']
            if not data:return
            try:
                page=int(page_entry.get_text())
                if not 1<=page<=data['pages']:raise ValueError()
            except ValueError:
                result.set_text(self.t('lookup_invalid_page').format(pages=number(data['pages'])));return
            load(page-1)

        def changed(*_):
            if state['normalizing']:return
            reset()
            if entry.get_text().strip():self.queue_search(load)
        entry.connect('changed',changed);entry.connect('activate',lambda *_:load(normalize=True))
        button.connect('clicked',lambda *_:load(normalize=True))
        first.connect('clicked',lambda *_:load())
        previous.connect('clicked',lambda *_:load(state['result']['page']-1))
        next_button.connect('clicked',lambda *_:load(state['result']['page']+1))
        last.connect('clicked',lambda *_:load(state['result']['pages']-1))
        go.connect('clicked',lambda *_:jump());page_entry.connect('activate',lambda *_:jump())
        self.lookup_controls={'entry':entry,'search':button,'status':result,'state':state,'scroll':scroll,
                              'first':first,'previous':previous,'next':next_button,'last':last,
                              'page':page_entry,'go':go,'page_label':page_label}
        entry.grab_focus()

    def frequency(self):
        self.show_statistics('periods')

    def show_statistics(self,kind):
        from .statistics_ui import StatisticsView
        if kind!='patterns':self.set_game('joker' if kind=='joker' else 'lotto')
        if not hasattr(self,'statistics_pages'):self.statistics_pages={}
        self.statistics_pages[self.game]=kind
        self.clear(self.game.capitalize()+' · '+self.t('s_'+kind),pinned=False,view='statistics');self.statistics_view=StatisticsView(self,kind)

    def message(self,title,text,icon=None):
        win=Gtk.Window(title=title,transient_for=self.window,modal=True,default_width=540)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=15)
        for side in ('start','end','top','bottom'):getattr(box,'set_margin_'+side)(20)
        if icon:
            picture=Gtk.Picture.new_for_filename(str(icon));picture.set_size_request(80,80);picture.set_halign(Gtk.Align.START);box.append(picture)
        heading=watch_errors(Gtk.Label(label=title,xalign=0));heading.add_css_class('title-2');box.append(heading)
        l=watch_errors(Gtk.Label(label=text,wrap=True,selectable=True,xalign=0),title);box.append(l)
        b=Gtk.Button(label=self.t('close'),halign=Gtk.Align.END);b.connect('clicked',lambda *_:win.close());box.append(b);win.set_child(box);win.present()

    def about(self):
        dialog=Gtk.AboutDialog(transient_for=self.window,modal=True,program_name='6 aus 45',version=VERSION,authors=['Josef Lehner'],website='https://dogtruck.eu',license_type=Gtk.License.GPL_3_0_ONLY)
        dialog.set_title(self.t('about_title'))
        dialog.set_logo(Gdk.Texture.new_from_filename(str(ROOT/'resources/icon.png')))
        dialog.present()

    def info(self):
        import subprocess
        try:
            import cairo
            cairo_info=f'Cairo {cairo.cairo_version_string()} · Cairo Team\nPycairo {cairo.version} · Pycairo Team'
        except ImportError:cairo_info='Cairo/Pycairo: '+self.t('not_installed')
        try:
            import matplotlib
            cairo_info+='\nMatplotlib '+matplotlib.__version__+' · Matplotlib Development Team'
        except ImportError:cairo_info+='\nMatplotlib: '+self.t('not_installed')
        try: pdf=subprocess.run(['pdftotext','-v'],capture_output=True,text=True,check=True).stderr.splitlines()[0]
        except (OSError,subprocess.SubprocessError,IndexError): pdf='pdftotext: '+self.t('not_installed')
        self.message(self.t('info_title'),f'6 aus 45 {VERSION}\nPython {platform.python_version()} · Python Software Foundation\nGTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()} · GTK Team\nPyGObject {gi.__version__} · PyGObject Team\nSQLite {sqlite3.sqlite_version} · SQLite Team\n'+cairo_info+'\n'+pdf+'\n'+self.t('pdf_info'),ROOT/'resources/info-3d.png')

    def help(self):
        self.refresh_language();path=ROOT/'help'/f"{self.config['language']}.html"
        if not path.is_file():raise ValueError('L004: '+self.t('missing_help'))
        webbrowser.open(path.as_uri())

    def logs(self):
        path=ROOT/'logs/error.log';self.message(self.t('logs'),format_log_dates(path.read_text()[-16000:]) if path.exists() else self.t('empty'))

    def background(self,job,done,with_result=False,on_error=None):
        if self.busy: self.notice.set_text(self.t('busy'));return
        self.busy=True;self.notice.set_text(self.t('busy'))
        def worker():
            try:
                result=job()
                def success():
                    self.busy=False;self.notice.set_text('✓ '+self.t('done'))
                    self.guard(lambda:done(result) if with_result else done())
                    self.update_statusbar()
                GLib.idle_add(success)
            except Exception as e:
                logging.exception('L001: Hintergrundaktion'); message=str(e)
                def failed():
                    self.busy=False;self.notice.set_text('L001: '+message)
                    if on_error: on_error(message)
                    else: self.message('L001',message+'\n'+self.t('error_help'))
                GLib.idle_add(failed)
        threading.Thread(target=worker,daemon=True).start()

    def preferences(self):
        self.refresh_language()
        win=Gtk.Window(title=self.t('language_help'),transient_for=self.window,modal=True,default_width=590)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        for side in ('start','end','top','bottom'):getattr(box,'set_margin_'+side)(20)
        box.append(Gtk.Label(label=self.t('tip_limit'),xalign=0))
        tip_limit=self.entry(text=str(self.config.get('max_tips',10000)));box.append(tip_limit)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        label=Gtk.Label(label=self.t('language'),xalign=0);box.append(label)
        codes=sorted(self.languages); dropdown=Gtk.DropDown.new_from_strings([self.languages[c].get('language_name',c)+' ('+c+')' for c in codes]);box.append(dropdown)
        if self.config['language'] in codes:dropdown.set_selected(codes.index(self.config['language']))
        dropdown.set_visible(len(codes)>1)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(Gtk.Label(label=self.t('download'),xalign=0))
        repo=self.entry(placeholder_text='owner/repository',text=self.config.get('repository',''));box.append(repo)
        code=self.entry(placeholder_text='de, en, …');box.append(code)
        status=watch_errors(Gtk.Label(label=self.t('download_hint'),wrap=True,xalign=0));box.append(status)
        download=Gtk.Button(label=self.t('download'),halign=Gtk.Align.START);box.append(download)
        def fetch():
            repository=repo.get_text().strip();language=code.get_text().strip()
            status.set_text(self.t('busy'))
            def done():
                self.refresh_language(); codes[:]=sorted(self.languages)
                dropdown.set_model(Gtk.StringList.new([self.languages[c].get('language_name',c)+' ('+c+')' for c in codes]));dropdown.set_visible(len(codes)>1)
                if language in codes:dropdown.set_selected(codes.index(language))
                status.set_text('✓ '+self.t('download_done'))
            self.background(lambda:settings.download(repository,language),done)
        download.connect('clicked',lambda *_:self.guard(fetch))
        save=Gtk.Button(label=self.t('save'),halign=Gtk.Align.END);box.append(save)
        def persist():
            limit=int(tip_limit.get_text())
            if not 1<=limit<=1000000:raise ValueError('L012: '+self.t('tip_limit'))
            self.config['max_tips']=limit
            if codes:self.config['language']=codes[dropdown.get_selected()]
            self.config['repository']=repo.get_text().strip();settings.save(self.config);self.refresh_language();self.rebuild();win.close()
        save.connect('clicked',lambda *_:self.guard(persist));win.set_child(box);win.present()

    def download_preferences(self,rebuild=False):
        """Quellen bearbeiten, Auswahl speichern und markierte Seiten importieren."""
        self.refresh_language()
        sources=archive_download.load_sources()
        win=Gtk.Window(title=self.t('recovery_new' if rebuild else 'archive_title'),transient_for=self.window,default_width=920,default_height=560)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        for side in ('start','end','top','bottom'):getattr(box,'set_margin_'+side)(18)
        title=Gtk.Label(label=self.t('archive_title'),xalign=0);title.add_css_class('title-2');box.append(title)
        hint=Gtk.Label(label=self.t('recovery_rebuild_hint' if rebuild else 'archive_hint'),xalign=0,wrap=True);box.append(hint)
        listing=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);box.append(listing)
        source_nav=Gtk.Box(spacing=8);box.append(source_nav)
        previous=Gtk.Button(label=self.t('previous_page'));following=Gtk.Button(label=self.t('next_page'))
        source_page=Gtk.Label();source_index=0
        for widget in (previous,source_page,following):source_nav.append(widget)
        controls=Gtk.Box(spacing=8);box.append(controls)
        status=watch_errors(Gtk.Label(label='',xalign=0,wrap=True,selectable=True));box.append(status)
        details=watch_errors(Gtk.Label(label='',xalign=0,yalign=0,wrap=True,selectable=True))
        # Das vollständige Ergebnis bleibt am Label abrufbar, die Anzeige zeigt
        # jeweils einen Eintrag. Damit wachsen lange Downloadprotokolle nicht aus dem Fenster.
        result_line=Gtk.Label(xalign=0,wrap=True,selectable=True);box.append(result_line)
        result_nav=Gtk.Box(spacing=8);box.append(result_nav)
        result_prev=Gtk.Button(label=self.t('previous_page'));result_next=Gtk.Button(label=self.t('next_page'))
        result_page=Gtk.Label();result_index=0;result_lines=[]
        for widget in (result_prev,result_page,result_next):result_nav.append(widget)
        def show_result(delta=0):
            nonlocal result_index
            result_index=max(0,min(result_index+delta,len(result_lines)-1))
            result_line.set_text(result_lines[result_index] if result_lines else '')
            result_nav.set_visible(len(result_lines)>1)
            result_page.set_text(f'{result_index+1} / {len(result_lines)}')
            result_prev.set_sensitive(result_index>0);result_next.set_sensitive(result_index+1<len(result_lines))
        def update_results(*_):
            nonlocal result_index,result_lines
            result_index=0;result_lines=details.get_text().splitlines();show_result()
        details.connect('notify::label',update_results)
        result_prev.connect('clicked',lambda *_:show_result(-1));result_next.connect('clicked',lambda *_:show_result(1))
        show_result()
        live=Gtk.Label(label=self.t('archive_background'),xalign=0,wrap=True);box.append(live)
        rows=[]
        def show_source(delta=0):
            nonlocal source_index
            source_index=max(0,min(source_index+delta,len(rows)-1))
            for index,item in enumerate(rows):item['row'].set_visible(index==source_index)
            source_page.set_text(f'{source_index+1 if rows else 0} / {len(rows)}')
            previous.set_sensitive(source_index>0);following.set_sensitive(source_index+1<len(rows))
        previous.connect('clicked',lambda *_:show_source(-1))
        following.connect('clicked',lambda *_:show_source(1))
        def clear_status(*_): status.set_text('')
        def append_row(source):
            row=Gtk.Box(spacing=18);row.add_css_class('section-panel')
            fields=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5,hexpand=True)
            row.append(fields)
            logo=Gtk.Picture(halign=Gtk.Align.END,valign=Gtk.Align.CENTER)
            logo.set_size_request(159,48)
            logo.set_can_shrink(True)
            row.append(logo)
            line=Gtk.Box(spacing=8);fields.append(line)
            enabled=Gtk.CheckButton(active=source['enabled']);enabled.set_tooltip_text(self.t('archive_active'))
            name=self.entry(text=source['name'],placeholder_text=self.t('archive_name'),width_chars=20)
            url=self.entry(text=source['url'],placeholder_text='https://…',hexpand=True)
            remove=Gtk.Button(label=self.t('remove'))
            entry={'row':row,'enabled':enabled,'name':name,'url':url,'source':source}
            rows.append(entry)
            for widget in (enabled,name,url,remove):line.append(widget)
            options=Gtk.Box(spacing=8);fields.append(options)
            game=Gtk.DropDown.new_from_strings(['auto','lotto','joker']);game.set_selected(['auto','lotto','joker'].index(source.get('game','auto')))
            fmt=Gtk.DropDown.new_from_strings(['auto','csv','pdf','json','html']);fmt.set_selected(['auto','csv','pdf','json','html'].index(source.get('format','auto')))
            priority=Gtk.SpinButton.new_with_range(0,999,1);priority.set_value(source.get('priority',50))
            for title,widget in [('source_game',game),('source_format',fmt),('source_priority',priority)]:
                options.append(Gtk.Label(label=self.t(title)));options.append(widget)
            entry.update(game=game,format=fmt,priority=priority)
            def update_logo(*_):
                # Nur echte Anbieter-Domains zuordnen; lokale Originalgrafik
                # vermeidet Netzwerkanfragen beim Öffnen und Bearbeiten.
                try:host=(urlsplit(url.get_text().strip()).hostname or '').lower()
                except ValueError:host=''
                asset=None;provider=''
                if host=='win2day.at' or host.endswith('.win2day.at'):
                    asset='win2day.svg';provider='win2day'
                elif host in ('github.com','raw.githubusercontent.com') or host.endswith('.github.com'):
                    asset='github.png';provider='GitHub'
                logo.set_visible(False);logo.set_paintable(None)
                if asset:
                    try:
                        pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT/'resources/site-logos'/asset),159,48,True)
                        texture=Gdk.Texture.new_for_pixbuf(pixbuf)
                        logo.set_paintable(texture);logo.set_tooltip_text(provider)
                        logo.set_visible(True)
                    except (GLib.Error,OSError) as error:
                        logging.warning('L001: Webseitenlogo %s nicht lesbar: %s. Grafik aus resources/site-logos wiederherstellen.',asset,error)
            url.connect('changed',update_logo);update_logo()
            enabled.connect('toggled',clear_status);name.connect('changed',clear_status);url.connect('changed',clear_status)
            def delete(*_):
                listing.remove(row);rows.remove(entry);clear_status();show_source()
            remove.connect('clicked',delete);listing.append(row);show_source()
        for source in sources:append_row(source)
        def values():
            return archive_download.validate_sources([{**r['source'],'name':r['name'].get_text().strip(),'url':r['url'].get_text().strip(),'enabled':r['enabled'].get_active(),'game':['auto','lotto','joker'][r['game'].get_selected()],
                'format':['auto','csv','pdf','json','html'][r['format'].get_selected()],'priority':r['priority'].get_value_as_int()} for r in rows])
        add=Gtk.Button(label=self.t('add_page'));save=Gtk.Button(label=self.t('save'));download=Gtk.Button(label=self.t('recovery_build' if rebuild else 'download_selected'))
        for button in (add,save,download):controls.append(button)
        database_link=Gtk.LinkButton.new_with_label('https://github.com/Franz-Dariwudel/Oesterreichisches-Zahlenlotto-6-aus-45/releases/latest/download/lotto-datenbank.zip',self.t('database_download'))
        database_link.set_halign(Gtk.Align.START);box.append(database_link)
        cancel_button=Gtk.Button(label=self.t('recovery_cancel'),halign=Gtk.Align.START)
        cancel_button.set_sensitive(False);cancel_button.set_visible(True);box.append(cancel_button)
        cancel_button.connect('clicked',lambda *_:(self.cancel_recovery(),self.operation_cancel.set()))
        def add_source(*_):
            nonlocal source_index
            append_row({'name':'','url':'','enabled':False});source_index=len(rows)-1;show_source()
        add.connect('clicked',add_source)
        def save_list():
            archive_download.save_sources(values());status.set_text('✓ '+self.t('sources_saved'))
        def guarded(callback):
            try:callback()
            except Exception as error:
                logging.warning('L007: Quellenliste: %s',type(error).__name__)
                status.set_text(str(error)+'\n'+self.t('archive_error_help'))
        save.connect('clicked',lambda *_:guarded(save_list))
        def start():
            if self.busy:status.set_text(self.t('busy'));return
            selected=values()
            if not any(source['enabled'] for source in selected):
                status.set_text(self.t('select_source'));return
            archive_download.save_sources(selected)
            controls.set_sensitive(False);listing.set_sensitive(False);details.set_text('');status.set_text(self.t('busy'))
            if rebuild:
                preferred=Path(self.db);cancel_button.set_sensitive(True)
                def recovered(result,error,cancelled):
                    controls.set_sensitive(True);listing.set_sensitive(True);cancel_button.set_sensitive(False)
                    status.set_text(self.notice.get_text())
                    if result:details.set_text('\n'.join(e['url']+'\n'+e['message'] for e in result['errors']))
                self.start_recovery(lambda cancel,notify:recovery.rebuild(selected,preferred,cancel,notify),
                    on_done=recovered,on_progress=status.set_text)
                return
            self.operation_cancel=threading.Event();cancel_button.set_sensitive(True)
            def progress(event,value):
                def show():status.set_text(self.t('archive_progress_'+event)+': '+value)
                GLib.idle_add(show)
            def failed(message):
                controls.set_sensitive(True);listing.set_sensitive(True)
                status.set_text('L008: '+message+'\n'+self.t('archive_error_help'))
            def done(result):
                controls.set_sensitive(True);listing.set_sensitive(True)
                unchanged=sum(bool(f.get('bereits_importiert')) for f in result['files'])
                notes=sum(f.get('konflikte',0)+f.get('parser_hinweise',0) for f in result['files'])
                changes=sum(f.get('aenderungen',0) for f in result['files'])
                message=self.t('archive_result').format(files=len(result['files']),unchanged=unchanged,changes=changes,notes=notes,errors=len(result['errors']))
                status.set_text(('L008: ' if result['errors'] else '✓ ' if not notes else '')+message)
                self.notice.set_text(status.get_text())
                lines=[f['name']+' · '+self.t('archive_unchanged' if f.get('bereits_importiert') else 'archive_imported') for f in result['files']]
                lines.extend(e['url']+'\n'+e['message'] for e in result['errors'])
                details.set_text('\n'.join(lines));self.home()
            self.background(lambda:archive_download.download_selected(selected,self.db,progress=progress,cancel=self.operation_cancel),done,with_result=True,on_error=failed)
        download.connect('clicked',lambda *_:guarded(start))
        # Referenzen dienen auch der GTK-Integrationsprüfung ohne Mauskoordinaten.
        self.source_dialog=win
        self.source_editor={'rows':rows,'add':add,'save':save,'download':download,'status':status,'details':details,'cancel':cancel_button,'previous':previous,'next':following,'page':source_page}
        win.set_child(box);win.present()

    def game_action(self,game,callback):
        self.set_game(game);callback()

    def show_tips(self,history=False):
        from .tips_ui import TipsView
        TipsView(self,history)

    def profile_action(self,action):
        view=getattr(self,'tip_view',None)
        if view is None or not hasattr(view,'saved') or self.current_view!='tips' or view.game!=self.game:
            self.show_tips();return
        getattr(view,action+'_profile')()


    def save_tips(self):
        view=getattr(self,'tip_view',None)
        if not view or view.game!=self.game or not view.batch:self.show_tips(True)
        else:view.export()

    def print_tips(self):
        from .exports import print_batch
        view=getattr(self,'tip_view',None)
        if not view or view.game!=self.game or not view.batch:self.show_tips(True)
        else:print_batch(view.batch,self.window,self.config['language'])

    def save_file(self,name,callback,background=True):
        chooser=Gtk.FileChooserNative(title=self.t('save'),transient_for=self.window,
            action=Gtk.FileChooserAction.SAVE,accept_label=self.t('save'),cancel_label=self.t('close'))
        chooser.set_current_name(name)
        def chosen(dialog,response):
            file=dialog.get_file() if response==Gtk.ResponseType.ACCEPT else None
            dialog.destroy()
            if file and file.get_path():
                if background:self.background(lambda:callback(Path(file.get_path())),lambda:self.notice.set_text('✓ '+self.t('done')))
                else:
                    def save():
                        callback(Path(file.get_path()));self.notice.set_text('✓ '+self.t('done'))
                    self.guard(save)
        chooser.connect('response',chosen);self.save_chooser=chooser;chooser.show()




    def db_check(self):
        from .services import check
        self.background(lambda:check(self.db),lambda:self.update_statusbar())

    def db_backup(self):
        from .services import backup
        from datetime import datetime
        self.save_file('lotto_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite3',lambda path:backup(self.db,path))

    def diagnose(self):
        from .services import diagnose
        from .exports import atomic_target
        import json
        def write(path):
            data=diagnose(self.db)
            with atomic_target(path) as temporary:temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        self.save_file('6aus45_diagnose.json',write)

    def import_log(self):
        from .services import import_log
        self.clear(self.t('import_log'),game_specific=False)
        rows=import_log(self.db)
        self.grid([self.t('s_date'),self.t('source'),self.t('status'),self.t('changes')],
                  [(format_timestamp(r['started']),r['url'],r['status'],r['details']) for r in rows])

    def update_statusbar(self):
        from .services import status
        if not hasattr(self,'statusbar'):return
        try:
            state=status(self.db);m=state['metadata']
            self.statusbar.set_text(self.t('status_line').format(lotto=state['counts']['lotto'],joker=state['counts']['joker'],
                check=format_timestamp(m.get('last_data_check')),update=format_timestamp(m.get('last_update')),internet=m.get('internet',self.t('not_checked'))))
        except Exception:self.statusbar.set_text(self.t('database_invalid'))

    def check_data(self):
        from .services import update_check_report
        if self.busy:return
        self.operation_cancel=threading.Event()
        self.clear(self.t('check_data'),game_specific=False)
        panel=Gtk.Box(spacing=24)
        panel.add_css_class('section-panel');self.content.append(panel)
        steps=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True,valign=Gtk.Align.CENTER)
        panel.append(steps)
        # Vorhandenes Projektlogo lokal und proportional rechts anzeigen.
        try:
            pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT/'resources/logo-6aus45-v1.png'),180,120,True)
            logo=Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            logo.set_size_request(180,120);logo.set_can_shrink(True)
            logo.set_halign(Gtk.Align.END);logo.set_valign(Gtk.Align.CENTER)
            logo.set_tooltip_text('6 aus 45');panel.append(logo)
        except (GLib.Error,OSError) as error:
            logging.warning('L001: Programmlogo nicht lesbar: %s. resources/logo-6aus45-v1.png wiederherstellen.',error)
        step_titles={'probe_sources':'probe_sources','check_data':'combined_download','db_check':'db_check','diagnose':'diagnose'}
        step_labels={};step_states={key:'waiting' for key in step_titles}
        def set_step(key,state):
            step_states[key]=state
            symbol={'waiting':'○','running':'…','ok':'✓','error':'⚠','stopped':'—'}[state]
            step_labels[key].set_text(f"{symbol} {self.t(step_titles[key])} · {self.t('combined_'+state)}")
        for key in step_titles:
            step_labels[key]=self.label('',steps);set_step(key,'waiting')
        self.check_steps=step_labels
        progress=self.label(self.t('busy'))
        cancel=Gtk.Button(label=self.t('recovery_cancel'),halign=Gtk.Align.START);self.content.append(cancel)
        cancel.connect('clicked',lambda *_:self.operation_cancel.set())
        def notify(event,value):
            def apply():
                if event=='phase':
                    set_step(value,'running');progress.set_text(self.t(step_titles[value]))
                elif event=='phase_result':
                    key,state=value;set_step(key,'ok' if state=='ok' else 'error')
                else:progress.set_text(self.t('archive_progress_'+event)+': '+value)
                return False
            GLib.idle_add(apply)
        def done(result):
            cancel.set_sensitive(False)
            for key,state in result.get('stages',{}).items():set_step(key,'ok' if state=='ok' else 'error')
            unchanged=sum(bool(f.get('bereits_importiert')) for f in result['files'])
            text=self.t('archive_result').format(files=len(result['files']),unchanged=unchanged,
                changes=sum(f.get('aenderungen',0) for f in result['files']),
                notes=sum(f.get('konflikte',0)+f.get('parser_hinweise',0) for f in result['files']),errors=len(result['errors']))
            progress.set_text(('⚠ ' if result['errors'] else '✓ ')+text+'\n'+'\n'.join(e['message'] for e in result['errors']))
            for source in result.get('source_checks',[]):
                text+='\n'+source['name']+': '+source['status']
            progress.set_text(('⚠ ' if result['errors'] else '✓ ')+text+'\n'+'\n'.join(e['message'] for e in result['errors']))
            summary='\n'+self.t('combined_database_ok' if result['database_ok'] else 'combined_database_failed')
            if result['report_path']:summary+='\n'+self.t('combined_report_saved').format(path=result['report_path'])
            progress.set_text(progress.get_text()+summary)
            self.notice.set_text(progress.get_text());self.update_statusbar()
        def failed(message):
            cancel.set_sensitive(False);progress.set_text(message)
            for key,state in step_states.copy().items():
                if state in ('waiting','running'):set_step(key,'stopped' if self.operation_cancel.is_set() or state=='waiting' else 'error')
        self.background(lambda:update_check_report(self.db,archive_download.load_sources(),ROOT/'logs',progress=notify,cancel=self.operation_cancel),done,True,failed)

    def probe_sources(self):
        import json
        self.background(lambda:archive_download.probe_sources(archive_download.load_sources()),
                        lambda data:self.message(self.t('probe_sources'),json.dumps(data,ensure_ascii=False,indent=2)),True)

    def local_import(self):
        chooser=Gtk.FileChooserNative(title=self.t('local_import'),transient_for=self.window,action=Gtk.FileChooserAction.OPEN,
            accept_label=self.t('local_import'),cancel_label=self.t('close'))
        def chosen(dialog,response):
            file=dialog.get_file() if response==Gtk.ResponseType.ACCEPT else None;dialog.destroy()
            if not file or not file.get_path():return
            path=Path(file.get_path())
            def work():
                from .database import ingest
                raw=path.read_bytes();records,issues=archive_download.parse_archive(raw,path.name)
                with closing(connect(self.db)) as con:return ingest(con,raw,path.name,records,issues)
            self.background(work,lambda result:self.message(self.t('local_import'),str(result)),True)
        chooser.connect('response',chosen);self.import_chooser=chooser;chooser.show()



def run(db):
    application=App(db)
    try:
        from .services import startup
        fresh=startup(application.db)
        archive_download.ensure_standard_sources(ROOT)
        if fresh:application.config_error=application.t('new_database')
    except Exception as error:
        logging.exception('L011: Startprüfung')
        application.config_error=str(error)
    return application.run([])
