"""GTK-Statistikseiten: Hintergrundberechnung, sortierbare Tabellen und Seitenwahl."""
import logging
import threading
from gi.repository import Gtk,GLib
from .statistics import Analysis,load_draws,WINDOWS,CHARTS
from .draw_search import parse_draw_numbers
from .widgets import FixedTable,ResultArea,date_control
from .joker_statistics import JokerAnalysis,load_joker
from .date_display import format_date
from .tips import select_draws,validate,default_profile
from . import patterns
from .database import has_other_draw_kinds


class StatisticsView:
    PAGE_SIZE=100

    def __init__(self,app,kind):
        self.app=app;self.kind=kind;self.closed=False;self.cancel=threading.Event()
        self.analysis=None;self.report=None;self.rows=[];self.page=0;self.table=None
        self.sort_column=None;self.descending=False;self.chart=None
        self.top=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3);app.content.append(self.top)
        controls=Gtk.Box(spacing=3);controls.add_css_class('section-controls');self.top.append(controls)
        controls.append(Gtk.Label(label=app.t('s_window'),xalign=0))
        labels=[app.t('s_all')]+[app.t('s_last_n').format(n=n) for n in WINDOWS]
        self.window=Gtk.DropDown.new_from_strings(labels);controls.append(self.window)
        limits=(0,*WINDOWS);self.window.set_selected(0 if kind=='periods' else limits.index(getattr(app,'statistics_limit',0)))
        self.window.set_sensitive(kind!='periods')
        self.game=app.game
        filter_row=Gtk.Box(spacing=4);filter_row.add_css_class('section-controls');self.top.append(filter_row)
        self.period_fields={}
        for key in ('from','to','weekday','kind'):
            field=app.entry(width_chars=4 if key=='weekday' else 10,placeholder_text=app.t('tip_'+key),text='-1' if key=='weekday' else '')
            field.set_tooltip_text(app.t('tip_'+key));field.set_placeholder_text('')
            cell=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
            cell.append(Gtk.Label(label=app.t('tip_'+key).split(' (')[0],xalign=0))
            cell.append(date_control(field,app.t) if key in ('from','to') else field);filter_row.append(cell);self.period_fields[key]=field
            if key=='kind':
                self.kind_cell=cell;cell.set_visible(has_other_draw_kinds(app.db,self.game))
        cancel=Gtk.Button(label=app.t('recovery_cancel'));controls.append(cancel);cancel.connect('clicked',lambda *_:self.cancel.set())
        self.refresh=Gtk.Button(label=app.t('refresh'));controls.append(self.refresh)
        self.scope=app.label('',self.top);self.message=app.label(app.t('busy'),self.top)
        self.metrics=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3);self.metrics.add_css_class('section-panel');self.top.append(self.metrics)
        note_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3);note_box.add_css_class('section-panel');self.top.append(note_box)
        app.label(app.t('stat_notes'),note_box).add_css_class('heading')
        app.label(app.t('s_hint_'+kind),note_box)
        app.label(app.t('j_note' if self.game=='joker' else 's_note'),note_box)
        self.section=Gtk.DropDown(halign=Gtk.Align.START);self.top.append(self.section);self.section.set_visible(False)
        self.filter_box=Gtk.Box(spacing=4);self.top.append(self.filter_box)
        self.filter_box.append(Gtk.Label(label=app.t('s_filter'),xalign=0))
        self.filter=app.entry(hexpand=True,placeholder_text='07 23');self.filter_box.append(self.filter)
        self.filter_box.set_visible(False)
        self.navigation=Gtk.Box(spacing=4);self.navigation.add_css_class('section-controls');self.top.append(self.navigation)
        self.first=Gtk.Button(label=app.t('first_page'));self.previous=Gtk.Button(label=app.t('previous_page'))
        self.page_label=Gtk.Label();self.page_entry=app.entry(width_chars=5,max_width_chars=5)
        self.page_entry.set_tooltip_text(app.t('page_number'))
        self.go=Gtk.Button(label=app.t('go_page'));self.next=Gtk.Button(label=app.t('next_page'));self.last=Gtk.Button(label=app.t('last_page'))
        for widget in (self.first,self.previous,self.page_label,self.page_entry,self.go,self.next,self.last):self.navigation.append(widget)
        self.navigation.set_sensitive(False)
        self.scroll=ResultArea();self.scroll.set_size_request(-1,300);app.content.append(self.scroll)
        self.window.connect('notify::selected',lambda *_:self.reload())
        self.refresh.connect('clicked',lambda *_:self.reload())
        self.section.connect('notify::selected',lambda *_:self.select_table())
        self.filter.connect('changed',lambda *_:self.filter_rows())
        self.filter.connect('activate',lambda *_:self.normalize_filter())
        self.first.connect('clicked',lambda *_:self.display(0))
        self.previous.connect('clicked',lambda *_:self.display(self.page-1))
        self.next.connect('clicked',lambda *_:self.display(self.page+1))
        self.last.connect('clicked',lambda *_:self.display((len(self.rows)-1)//self.PAGE_SIZE))
        self.go.connect('clicked',lambda *_:self.jump());self.page_entry.connect('activate',lambda *_:self.jump())
        from .rule_settings_ui import RuleEditor
        self.rule_editor=RuleEditor(self)
        self.show_kind=False
        self.reload()

    def close(self):
        self.closed=True;self.cancel.set()
        if self.chart:self.chart.close()

    def fmt(self,value,kind='text'):
        if value is None:return '—'
        if kind=='pause':return ('≥' if value[1] else '')+self.fmt(value[0],'int')
        if kind=='kind':return self.app.t('s_main') if value=='haupt' else value
        if kind=='date':return format_date(value)
        if kind=='number':return f'{value:02d}'
        if kind=='numbers':return ' · '.join(f'{n:02d}' for n in value) if value else '—'
        if kind=='gaps':return ' · '.join(map(str,value)) if value else '—'
        if kind=='groups':return ' / '.join('–'.join(f'{n:02d}' for n in group) for group in value) if value else '—'
        if kind in ('int','float','signed','percent'):
            text=f'{value:,}' if kind=='int' else f'{value:+,.2f}' if kind=='signed' else f'{value:,.2f}'
            if self.app.config['language']=='de':text=text.replace(',','_').replace('.',',').replace('_','.')
            return text+(' %' if kind=='percent' else '')
        return str(value)

    def reload(self):
        if self.closed:return
        self.cancel.set();cancel=threading.Event();self.cancel=cancel
        limit=(0,*WINDOWS)[self.window.get_selected()]
        if self.kind=='periods':limit=0
        else:self.app.statistics_limit=limit
        self.analysis=None;self.report=None;self.table=None;self.rows=[]
        if self.chart:self.chart.close();self.chart=None
        self.message.set_text(self.app.t('busy'));self.scope.set_text('')
        self.scroll.set_child(None);self.navigation.set_sensitive(False);self.section.set_visible(False);self.filter_box.set_visible(False)
        while child:=self.metrics.get_first_child():self.metrics.remove(child)
        def ready(analysis,report,error=None,show_kind=False):
            if self.closed or cancel.is_set():return False
            if error:
                self.message.set_text('L001: '+error+'\n'+self.app.t('s_error'));return False
            self.analysis=analysis;self.report=report;self.show_kind=show_kind
            self.kind_cell.set_visible(show_kind);self.rule_editor.kind_cell.set_visible(show_kind)
            self.active_scope=' · '.join(f'{self.app.t("tip_"+k)}: {v}' for k,v in profile.items() if k in ('from','to','weekday','kind') and v not in ('',-1))
            self.scope.set_text(self.app.t('j_scope' if self.game=='joker' else 's_scope').format(count=self.fmt(report['count'],'int'),available=self.fmt(report['available'],'int'),
                first=self.fmt(report['first'],'date'),last=self.fmt(report['last'],'date'))+' · '+self.active_scope)
            self.metrics.set_visible(bool(report['metrics']))
            for title,value,fmt in report['metrics']:self.app.label(self.app.t(title)+': '+self.fmt(value,fmt),self.metrics)
            if self.kind=='charts':self.build_charts()
            else:
                tables=report['tables'];self.section.set_model(Gtk.StringList.new([self.app.t(t.title) for t in tables]))
                self.section.set_selected(0);self.section.set_visible(len(tables)>1);self.select_table()
            if self.kind=='patterns':self.pattern_controls()
            return False
        try:
            profile=default_profile(self.game)
            for key,field in self.period_fields.items():profile[key]=int(field.get_text()) if key=='weekday' else field.get_text().strip()
            profile=validate(profile)
        except ValueError as error:self.message.set_text(str(error));return
        def worker():
            try:
                all_draws=load_joker(self.app.db,cancel) if self.game=='joker' else load_draws(self.app.db,cancel)
                show_kind=any((d[2] if self.game=='joker' else d.kind)!='haupt' for d in all_draws)
                draws=select_draws(all_draws,profile)
                analysis=JokerAnalysis(draws,limit,cancel) if self.game=='joker' else Analysis(draws,limit,cancel)
                report=patterns.analyse(analysis.draws,self.game) if self.kind=='patterns' else analysis.report(self.kind)
                GLib.idle_add(ready,analysis,report,None,show_kind)
            except Exception as error:
                if not cancel.is_set():
                    logging.exception('L001: Statistik');GLib.idle_add(ready,None,None,str(error))
        threading.Thread(target=worker,daemon=True).start()

    def select_table(self):
        if not self.report or self.kind=='charts':return
        index=self.section.get_selected()
        if index>=len(self.report['tables']):return
        if self.chart:self.chart.close();self.chart=None
        self.table=self.report['tables'][index];self.sort_column=None;self.descending=False
        self.filter_box.set_visible(self.table.filter_column is not None)
        self.filter.set_text('');self.filter_rows()

    def filter_rows(self):
        if not self.table:return
        rows=self.table.rows
        if self.table.filter_column is not None:
            try:numbers=parse_draw_numbers(self.filter.get_text())
            except ValueError:
                self.rows=[];self.scroll.set_child(None);self.navigation.set_sensitive(False)
                self.message.set_text(self.app.t('history_numbers_invalid'));return
            if numbers:rows=[row for row in rows if set(numbers).issubset(row[self.table.filter_column])]
        self.rows=list(rows)
        if self.sort_column is not None:
            index=self.sort_column
            self.rows=sorted((r for r in rows if r[index] is not None),key=lambda r:r[index],reverse=self.descending)+[r for r in rows if r[index] is None]
        self.display(0)

    def normalize_filter(self):
        try:numbers=parse_draw_numbers(self.filter.get_text())
        except ValueError:return
        self.filter.set_text(' '.join(f'{n:02d}' for n in numbers))

    def sort(self,index):
        self.descending=not self.descending if self.sort_column==index else False
        self.sort_column=index;self.filter_rows()

    def display(self,page):
        if self.closed or not self.table:return
        total=len(self.rows);pages=max(1,(total+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        page=max(0,min(page,pages-1));self.page=page
        # Originalspalten und Sortierindizes erhalten; nur die Darstellung kürzen.
        visible=[i for i,(_,fmt) in enumerate(self.table.columns) if fmt!='kind' or self.show_kind]
        self.visible_columns=visible
        headers=[self.app.t(self.table.columns[i][0]) for i in visible]
        rows=[[self.fmt(row[i],self.table.columns[i][1]) for i in visible] for row in self.rows[page*self.PAGE_SIZE:(page+1)*self.PAGE_SIZE]]
        align=[1 if self.table.columns[i][1] in ('int','number','float','signed','percent','pause') else 0 for i in visible]
        selected=visible.index(self.sort_column) if self.sort_column in visible else None
        table=FixedTable(headers,rows,align,sort=lambda index:self.sort(visible[index]),selected=selected,descending=self.descending)
        self.scroll.set_child(table)
        self.navigation.set_sensitive(total>0)
        self.first.set_sensitive(page>0);self.previous.set_sensitive(page>0)
        self.next.set_sensitive(page+1<pages);self.last.set_sensitive(page+1<pages)
        self.page_label.set_text(self.app.t('lookup_page').format(page=page+1,pages=pages));self.page_entry.set_text(str(page+1))
        if not self.report['count']:self.message.set_text(self.app.t('j_empty' if self.game=='joker' else 's_empty'))
        elif not total:self.message.set_text(self.app.t('s_no_rows'))
        else:self.message.set_text('✓ '+self.app.t('s_rows').format(total=self.fmt(total,'int'),first=self.fmt(page*self.PAGE_SIZE+1,'int'),last=self.fmt(min((page+1)*self.PAGE_SIZE,total),'int')))

    def jump(self):
        pages=max(1,(len(self.rows)+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        try:
            page=int(self.page_entry.get_text())
            if not 1<=page<=pages:raise ValueError()
        except ValueError:
            self.message.set_text(self.app.t('lookup_invalid_page').format(pages=pages));return
        self.display(page-1)

    def build_charts(self):
        self.navigation.set_visible(False)
        if not hasattr(self,'chart_controls'):
            self.chart_controls=Gtk.Box(spacing=3);self.top.append(self.chart_controls)
            self.chart_select=Gtk.DropDown.new_from_strings([self.app.t('s_chart_'+kind) for kind in CHARTS]);self.chart_controls.append(self.chart_select)
            self.chart_number_label=Gtk.Label(label=self.app.t('s_number'));self.chart_controls.append(self.chart_number_label)
            self.chart_number=self.app.entry(text='01',width_chars=3,max_width_chars=4,input_purpose=Gtk.InputPurpose.DIGITS)
            self.chart_number.set_tooltip_text(self.app.t('chart_number_help'));self.chart_controls.append(self.chart_number)
            self.chart_hint=self.app.label('',self.top)
            self.chart_select.connect('notify::selected',lambda *_:self.update_chart())
            self.chart_number.connect('changed',lambda *_:self.update_chart())
            self.chart_number.connect('activate',lambda *_:self.normalize_chart_number())
        self.update_chart()

    def normalize_chart_number(self):
        text=self.chart_number.get_text().strip()
        if text.isascii() and text.isdigit() and 1<=int(text)<=45:
            self.chart_number.set_text(f'{int(text):02d}')
        self.update_chart()

    def update_chart(self):
        if self.closed or not self.analysis:return
        try:
            from .plotting import Chart
        except (ImportError,ValueError) as error:
            logging.exception('L001: Diagrammmodul');self.message.set_text(self.app.t('s_chart_missing'));return
        if self.chart:self.chart.close()
        kind=CHARTS[self.chart_select.get_selected()];number=1
        self.chart_number.set_visible(kind in ('timeline','deviation','rolling','zscore'));self.chart_number_label.set_visible(kind in ('timeline','deviation','rolling','zscore'))
        if kind in ('timeline','deviation','rolling','zscore'):
            try:
                text=self.chart_number.get_text().strip()
                if not text.isascii() or not text.isdigit() or not 1<=int(text)<=45:raise ValueError()
                number=int(text)
            except ValueError:
                self.chart=None;self.scroll.set_child(None);self.message.set_text(self.app.t('chart_number_invalid'));return
        self.chart_hint.set_text(self.app.t('s_chart_hint_'+kind))
        data=self.analysis.chart(kind,number)
        self.chart=Chart(data,self.app.t,self.fmt,self.scope.get_text());self.scroll.set_size_request(-1,760 if data['kind']=='heatmap' else 300);self.scroll.set_child(self.chart)
        self.message.set_text('✓ '+self.app.t('s_chart_ready') if self.analysis.n else self.app.t('j_empty' if self.game=='joker' else 's_empty'))

    def pattern_controls(self):
        if not hasattr(self,'pattern_row'):
            self.pattern_row=Gtk.Box(spacing=4);self.top.append(self.pattern_row)
            self.pattern_keys=list(self.report['series'])+(['positions','transitions','weekdays'] if self.game=='joker' else [])
            self.pattern_select=Gtk.DropDown.new_from_strings([self.app.t('pattern_'+key) for key in self.pattern_keys]);self.pattern_row.append(self.pattern_select)
            button=Gtk.Button(label=self.app.t('show_chart'));self.pattern_row.append(button)
            button.connect('clicked',lambda *_:self.app.guard(self.pattern_chart))
            table=Gtk.Button(label=self.app.t('show_table'));self.pattern_row.append(table)
            table.connect('clicked',lambda *_:self.select_table())

    def pattern_chart(self):
        from .plotting import Chart
        if not self.report:return
        key=self.pattern_keys[self.pattern_select.get_selected()]
        data=patterns.chart(self.report,key)
        if self.chart:self.chart.close()
        self.chart=Chart(data,self.app.t,self.fmt,self.scope.get_text());self.scroll.set_size_request(-1,760 if data['kind']=='heatmap' else 300);self.scroll.set_child(self.chart)

