"""GTK-Quotenansicht mit Live-Datumsfilter, Seitenwahl und festen Kopfzeilen."""
import logging
import threading
from contextlib import closing
from gi.repository import Gtk,GLib
from .database import connect,has_other_draw_kinds
from .draw_search import parse_date_filter
from .date_display import format_date
from .quotes import search_quotes,group_months
from .widgets import date_control,FixedTable,ResultArea


class QuotesView:
    PAGE_SIZE=100

    def __init__(self,app):
        self.app=app;self.game=app.game;self.rows=[];self.current_rows=[];self.page=0;self.pages=0
        self.months={};self.month_buttons={};self.year_expanders={};self.selected_month=None
        self.cancel=None;self.closed=False
        t=app.t
        app.label(t('quotes_hint'))
        inputs=Gtk.Box(spacing=8);inputs.add_css_class('section-controls');app.content.append(inputs)
        inputs.append(Gtk.Label(label=t('quotes_date')))
        self.entry=app.entry(placeholder_text='TT.MM.JJJJ',width_chars=10)
        self.search=Gtk.Button(label=t('search'));self.latest=Gtk.Button(label=t('quotes_latest'))
        self.all=Gtk.Button(label=t('quotes_all'))
        for widget in (date_control(self.entry,t),self.search,self.latest,self.all):inputs.append(widget)
        extra=Gtk.Box(spacing=8);extra.add_css_class('section-controls');app.content.append(extra)
        self.weekday=Gtk.DropDown.new_from_strings([t('s_all'),'Mo','Di','Mi','Do','Fr','Sa','So']);extra.append(self.weekday)
        self.kind_entry=app.entry(placeholder_text=t('tip_kind'));extra.append(self.kind_entry)
        self.kind_entry.set_visible(has_other_draw_kinds(app.db,self.game))
        self.weekday.connect('notify::selected',self.changed);self.kind_entry.connect('changed',self.changed)
        self.status=app.label('')
        self.navigation=Gtk.Box(spacing=8);app.content.append(self.navigation)
        self.first=Gtk.Button(label=t('first_page'));self.previous=Gtk.Button(label=t('previous_page'))
        self.next=Gtk.Button(label=t('next_page'));self.last=Gtk.Button(label=t('last_page'))
        self.page_label=Gtk.Label();self.page_entry=app.entry(width_chars=5,max_width_chars=5)
        self.page_entry.set_tooltip_text(t('page_number'));self.go=Gtk.Button(label=t('go_page'))
        for widget in (self.first,self.previous,self.page_label,self.page_entry,self.go,self.next,self.last):self.navigation.append(widget)
        results=Gtk.Box(spacing=18,vexpand=True);app.content.append(results)
        self.browser=Gtk.ScrolledWindow(min_content_width=165,vexpand=True)
        self.browser.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        results.append(self.browser);self.browser.set_visible(False)
        right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,hexpand=True,vexpand=True);results.append(right)
        self.month_heading=app.label('',right);self.month_heading.add_css_class('heading');self.month_heading.set_visible(False)
        self.area=ResultArea();right.append(self.area)
        self.changed_id=self.entry.connect('changed',self.changed)
        self.entry.connect('activate',lambda *_:app.guard(self.load))
        self.search.connect('clicked',lambda *_:app.guard(self.load))
        self.latest.connect('clicked',lambda *_:app.guard(lambda:self.load(latest=True)))
        self.all.connect('clicked',lambda *_:app.guard(self.show_all))
        for button,number in ((self.first,lambda:0),(self.previous,lambda:self.page-1),
                              (self.next,lambda:self.page+1),(self.last,lambda:self.pages-1)):
            button.connect('clicked',lambda _,page=number:app.guard(lambda:self.display(page())))
        self.go.connect('clicked',lambda *_:app.guard(self.jump))
        self.page_entry.connect('activate',lambda *_:app.guard(self.jump))
        self.load(latest=True)

    def close(self):
        self.closed=True
        if self.cancel:self.cancel.set()

    def reset(self):
        self.app.cancel_searches()
        if self.cancel:self.cancel.set()
        self.cancel=None;self.rows=[];self.current_rows=[];self.pages=0;self.page=0
        self.months={};self.month_buttons={};self.year_expanders={};self.selected_month=None
        self.navigation.set_sensitive(False);self.page_label.set_text('');self.page_entry.set_text('')
        self.navigation.set_visible(False)
        self.status.set_text('');self.area.set_child(None)
        self.browser.set_visible(False);self.browser.set_child(None);self.month_heading.set_visible(False)

    def changed(self,*_):
        self.reset();self.app.queue_search(self.load)

    def show_all(self):
        self.entry.handler_block(self.changed_id);self.entry.set_text('');self.entry.handler_unblock(self.changed_id)
        self.load()

    def load(self,latest=False):
        self.reset()
        try:query=parse_date_filter('' if latest else self.entry.get_text())
        except ValueError:
            self.status.set_text(self.app.t('history_invalid'));return
        all_months=not latest and not self.entry.get_text().strip()
        weekday=self.weekday.get_selected()-1;kind=self.kind_entry.get_text().strip()
        cancel=threading.Event();self.cancel=cancel;db=self.app.db
        self.status.set_text(self.app.t('busy'))

        def complete(rows=None,date=None,error=None):
            if self.closed or cancel.is_set() or self.cancel is not cancel:return False
            self.cancel=None
            if error:
                self.status.set_text('L001: '+error+'\n'+self.app.t('error_help'));return False
            if latest:
                self.entry.handler_block(self.changed_id)
                self.entry.set_text(format_date(date,weekday=False) if date else '')
                self.entry.handler_unblock(self.changed_id)
            self.rows=rows;self.current_rows=rows;self.pages=(len(rows)+self.PAGE_SIZE-1)//self.PAGE_SIZE
            if rows:self.app.guard(self.build_months if all_months else lambda:self.display(0))
            else:self.status.set_text(self.app.t('quotes_empty'))
            return False

        def worker():
            try:
                date=None;active_query=query
                with closing(connect(db,create=False)) as con:
                    con.set_progress_handler(lambda:int(cancel.is_set()),1000);con.execute('BEGIN')
                    if latest:
                        date=con.execute(f'''SELECT max(d.datum) FROM {self.game}_ziehungen d
                            JOIN {self.game}_quoten q ON q.ziehung_id=d.id''').fetchone()[0]
                        active_query=parse_date_filter(format_date(date,weekday=False) if date else '')
                    rows=search_quotes(con,self.game,active_query)
                    from datetime import date as calendar_date
                    rows=[r for r in rows if (weekday==-1 or calendar_date.fromisoformat(r['datum']).weekday()==weekday) and (not kind or r['kennung']==kind)]
                GLib.idle_add(complete,rows,date)
            except Exception as error:
                if not cancel.is_set():
                    logging.exception('L001: Gewinnquoten');GLib.idle_add(complete,None,None,str(error))
        threading.Thread(target=worker,daemon=True).start()

    def build_months(self):
        """Jahre aufklappen, Monate auswählen; die Quoten rechts behalten feste Köpfe."""
        self.months=group_months(self.rows)
        listing=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.app.label(self.app.t('quotes_year_month'),listing).add_css_class('heading')
        self.browser.set_child(listing);self.browser.set_visible(True)
        for year in dict.fromkeys(month[:4] for month in self.months):
            expander=Gtk.Expander(label=year);listing.append(expander);self.year_expanders[year]=expander
            def expand(widget,_,y=year):
                if not widget.get_expanded() or widget.get_child() is not None:return
                box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_start=12)
                for month in self.months:
                    if not month.startswith(y):continue
                    button=Gtk.ToggleButton(label=format_date(month))
                    if self.month_buttons:button.set_group(next(iter(self.month_buttons.values())))
                    self.month_buttons[month]=button;box.append(button)
                    button.connect('toggled',lambda b,m=month:self.app.guard(lambda:self.select_month(m)) if b.get_active() else None)
                widget.set_child(box)
            expander.connect('notify::expanded',expand)
        first=next(iter(self.months));self.year_expanders[first[:4]].set_expanded(True)
        self.month_buttons[first].set_active(True)

    def select_month(self,month):
        self.selected_month=month;self.current_rows=self.months[month]
        self.pages=(len(self.current_rows)+self.PAGE_SIZE-1)//self.PAGE_SIZE
        self.month_heading.set_text(self.app.t('quotes_month').format(month=format_date(month)))
        self.month_heading.set_visible(True);self.display(0)

    def display(self,page):
        if not self.current_rows:return
        self.page=max(0,min(page,self.pages-1));start=self.page*self.PAGE_SIZE
        visible=self.current_rows[start:start+self.PAGE_SIZE];table=[]
        for row in visible:
            date=format_date(row['datum'])+(' · '+row['kennung'] if row['kennung']!='haupt' else '')
            values,_=self.app.quote_values(self.game,row['datum'],row)
            table.append([date,*values])
        self.area.set_child(FixedTable([self.app.t(key) for key in ('quotes_date','rank','winners','amount')],table,[0,0,1,1],
                                     row_groups=[row['id'] for row in visible]))
        self.navigation.set_sensitive(True)
        self.navigation.set_visible(True)
        self.first.set_sensitive(self.page>0);self.previous.set_sensitive(self.page>0)
        self.next.set_sensitive(self.page+1<self.pages);self.last.set_sensitive(self.page+1<self.pages)
        self.page_label.set_text(self.app.t('lookup_page').format(page=self.page+1,pages=self.pages))
        self.page_entry.set_text(str(self.page+1))
        self.status.set_text('✓ '+self.app.t('quotes_results').format(
            draws=len({r['id'] for r in self.current_rows}),quotes=len(self.current_rows),
            first=start+1,last=start+len(visible),total=len(self.current_rows)))

    def jump(self):
        try:
            page=int(self.page_entry.get_text())
            if not 1<=page<=self.pages:raise ValueError()
        except ValueError:
            self.status.set_text(self.app.t('lookup_invalid_page').format(pages=self.pages));return
        self.display(page-1)
