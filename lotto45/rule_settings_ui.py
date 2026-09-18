"""Einstellungen für Tippfilter direkt auf den zugeordneten Statistikseiten."""
from gi.repository import Gtk
from . import rule_settings as rules
from .widgets import date_control
from .date_display import format_date
from .database import has_other_draw_kinds


class RuleEditor:
    def __init__(self,view):
        self.view=view;self.app=app=view.app;self.game=view.game
        self.keys=[k for k in (*rules.DEFAULTS[self.game],'weight') if rules.page_for(self.game,k)==view.kind]
        self.fields={};self.scope_fields={}
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        box.add_css_class('section-panel');view.top.append(box);panel=box
        app.label(app.t('rule_settings_title'),box).add_css_class('heading')
        app.label(app.t('rule_settings_hint'),box)
        p=rules.load(app.config,self.game)
        grid=Gtk.Grid(column_spacing=6,row_spacing=3);box.append(grid)
        for i,key in enumerate(self.keys):
            grid.attach(Gtk.Label(label=app.t('tip_weight' if key=='weight' else 'rule_'+key),xalign=0),0,i,1,1)
            value=p['weight'] if key=='weight' else p['rules'][key]
            if key=='unusual':
                field=Gtk.Label(label=app.t('tip_unusual_description'),xalign=0,wrap=True)
            elif key=='palindrome':
                field=Gtk.DropDown.new_from_strings([app.t('tip_pal_'+v) for v in ('allow','avoid','only')])
                field.set_selected(('allow','avoid','only').index(value))
            else:field=app.entry(text=rules.describe(value),width_chars=10 if key=='decades' else 7)
            grid.attach(field,1,i,1,1);self.fields[key]=field
        app.label(app.t('rule_scope_title'),box)
        scope=Gtk.Grid(column_spacing=6,row_spacing=3,halign=Gtk.Align.START);box.append(scope)
        for i,key in enumerate(rules.SCOPE):
            field=app.entry(text=format_date(p[key],weekday=False) if key in ('from','to') and p[key] else str(p[key]),width_chars=4 if key=='weekday' else 10 if key in ('from','to','kind') else 6)
            cell=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
            label=Gtk.Label(label=app.t('tip_'+key).split(' (')[0],xalign=0);label.set_tooltip_text(app.t('tip_'+key));cell.append(label);cell.append(date_control(field,app.t) if key in ('from','to') else field);scope.attach(cell,i%3,i//3,1,1)
            self.scope_fields[key]=field
            if key=='kind':
                self.kind_cell=cell
                cell.set_visible(has_other_draw_kinds(app.db,self.game))
        button=Gtk.Button(label=app.t('rule_settings_save'),halign=Gtk.Align.START);panel.append(button)
        self.message=app.label('',panel);button.connect('clicked',lambda *_:app.guard(self.save))
        for field in (*self.fields.values(),*self.scope_fields.values()):
            if isinstance(field,Gtk.Entry):field.connect('changed',lambda *_:self.message.set_text(''))
            elif isinstance(field,Gtk.DropDown):field.connect('notify::selected',lambda *_:self.message.set_text(''))

    def save(self):
        p=rules.load(self.app.config,self.game)
        try:
            for key,field in self.fields.items():
                if key=='unusual':continue
                value=('allow','avoid','only')[field.get_selected()] if key=='palindrome' else rules.parse(key,field.get_text())
                if key=='weight':p[key]=value
                else:p['rules'][key]=value
            for key,field in self.scope_fields.items():
                p[key]=int(field.get_text()) if key in ('last','weekday') else field.get_text().strip()
        except ValueError as error:raise ValueError('L012: '+self.app.t('rule_input_error')) from error
        rules.save(self.app,self.game,p)
        self.message.set_text('✓ '+self.app.t('done'))
