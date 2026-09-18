"""GTK-Formular für zuschaltbare Regeln, Profile, Serien und Druck."""
import json
import threading
from gi.repository import Gtk,GLib
from . import tips,exports,settings,rule_settings
from .date_display import format_timestamp


class TipsView:
    def __init__(self,app,history=False):
        self.app=app;self.game=app.game;self.cancel=threading.Event();self.batch=None
        app.clear(self.game.capitalize()+' · '+app.t('tip_history' if history else 'tip_create'),view='tip_history' if history else 'tips')
        app.tip_view=self
        app.label(app.t('tip_warning'))
        if history:self.history();return
        row=Gtk.Box(spacing=8);row.add_css_class('section-controls');app.content.append(row)
        row.append(Gtk.Label(label=app.t('tip_count')))
        self.count=app.entry(text='6',width_chars=7);row.append(self.count)
        self.mode=Gtk.DropDown.new_from_strings([app.t('tip_random'),app.t('tip_filtered')]);row.append(self.mode)
        self.rule_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.rule_box.add_css_class('section-panel');app.content.append(self.rule_box)
        app.label(app.t('tip_rules'),self.rule_box).add_css_class('heading')
        self.rule_box.set_visible(False)
        self.entries={};self.checks={};self.rule_labels={}
        app.label(app.t('tip_rule_locations'),self.rule_box)
        self.rule_values=rule_settings.load(app.config,self.game)
        scope=' · '.join(app.t('tip_'+key)+': '+str(self.rule_values[key]) for key in rule_settings.SCOPE if self.rule_values[key] not in ('',-1) and (key!='last' or self.rule_values[key]!=0))
        self.scope_label=app.label(app.t('rule_scope_title')+': '+(scope or app.t('s_all')),self.rule_box)
        for key in (*rule_settings.DEFAULTS[self.game],'weight'):
            value=self.rule_values['weight'] if key=='weight' else self.rule_values['rules'][key]
            label=app.t('tip_weight' if key=='weight' else 'rule_'+key)
            page=app.t('s_'+rule_settings.page_for(self.game,key))
            if key=='palindrome':value=app.t('tip_pal_'+value)
            elif key=='unusual':value=app.t('tip_unusual_description')
            check=Gtk.CheckButton()
            text=Gtk.Label(label=f'{label}: {rule_settings.describe(value)} · {page}',wrap=True,max_width_chars=75,xalign=0)
            check.set_child(text);self.rule_labels[key]=text
            self.rule_box.append(check);self.checks[key]=check
        self.mode.connect('notify::selected',lambda *_:(self.rule_box.set_sensitive(self.mode.get_selected()==1),self.rule_box.set_visible(self.mode.get_selected()==1)))
        self.rule_box.set_sensitive(False)
        profile_row=Gtk.Box(spacing=8);profile_row.add_css_class('section-panel');app.content.append(profile_row)
        self.name=app.entry(placeholder_text=app.t('profile_name'));profile_row.append(self.name)
        self.saved=Gtk.DropDown.new_from_strings([]);profile_row.append(self.saved)
        self.names=[];self.reload_profiles()
        for key,callback in [('profile_load',self.load_profile),('profile_save',self.save_profile),('profile_delete',self.delete_profile)]:
            button=Gtk.Button(label=app.t(key));profile_row.append(button);button.connect('clicked',lambda *_,cb=callback:app.guard(cb))
        actions=Gtk.Box(spacing=8);actions.add_css_class('section-controls');app.content.append(actions)
        self.run=Gtk.Button(label=app.t('tip_create'));actions.append(self.run)
        cancel=Gtk.Button(label=app.t('recovery_cancel'));actions.append(cancel);cancel.connect('clicked',lambda *_:self.cancel.set())
        self.progress=Gtk.ProgressBar(show_text=True);app.content.append(self.progress)
        self.message=app.label('');self.result=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);app.content.append(self.result)
        self.run.connect('clicked',lambda *_:app.guard(self.generate))
        self.mode.connect('notify::selected',lambda *_:self.message.set_text(''))
        self.count.connect('changed',lambda *_:self.message.set_text(''))
        for field in self.entries.values():
            if isinstance(field,Gtk.Entry):field.connect('changed',lambda *_:self.message.set_text(''))
            elif isinstance(field,Gtk.DropDown):field.connect('notify::selected',lambda *_:self.message.set_text(''))
        for check in self.checks.values():check.connect('toggled',lambda *_:self.message.set_text(''))

    def profile(self):
        p=tips.default_profile(self.game);p['mode']='filtered' if self.mode.get_selected() else 'random'
        p['name']=self.name.get_text().strip()
        if p['mode']=='random':return p
        values=rule_settings.load(self.app.config,self.game)
        for key in rule_settings.SCOPE:p[key]=values[key]
        p['weight']=values['weight'] if self.checks['weight'].get_active() else 0.0
        p['rules']={key:values['rules'][key] for key,check in self.checks.items() if key!='weight' and check.get_active()}
        return tips.validate(p)

    def reload_profiles(self):
        self.names=[name for name,_ in tips.profiles(self.app.db,self.game)]
        self.saved.set_model(Gtk.StringList.new(self.names));self.saved.set_visible(bool(self.names))

    def load_profile(self):
        index=self.saved.get_selected()
        if index>=len(self.names):raise ValueError('L012: '+self.app.t('profile_missing'))
        name=self.names[index];p=dict(tips.profiles(self.app.db,self.game))[name]
        tips.validate(p);self.name.set_text(name);self.mode.set_selected(int(p['mode']=='filtered'))
        # Ein geladenes Profil übernimmt seine Werte in die Statistik-Einstellungen.
        # Werte abgeschalteter Regeln bleiben dabei erhalten.
        values=rule_settings.load(self.app.config,self.game)
        for key in rule_settings.SCOPE:values[key]=p[key]
        if p['weight']:values['weight']=p['weight']
        values['rules'].update(p['rules']);rule_settings.save(self.app,self.game,values)
        scope=' · '.join(self.app.t('tip_'+key)+': '+str(values[key]) for key in rule_settings.SCOPE if values[key] not in ('',-1) and (key!='last' or values[key]!=0))
        self.scope_label.set_text(self.app.t('rule_scope_title')+': '+(scope or self.app.t('s_all')))
        for key,check in self.checks.items():
            check.set_active(bool(p['weight']) if key=='weight' else key in p['rules'])
            value=values['weight'] if key=='weight' else values['rules'][key]
            if key=='palindrome':value=self.app.t('tip_pal_'+value)
            elif key=='unusual':value=self.app.t('tip_unusual_description')
            self.rule_labels[key].set_text(self.app.t('tip_weight' if key=='weight' else 'rule_'+key)+': '+rule_settings.describe(value)+' · '+self.app.t('s_'+rule_settings.page_for(self.game,key)))
        tips.save_profile(self.app.db,name,p)
        self.message.set_text('✓ '+self.app.t('done'))

    def save_profile(self):
        tips.save_profile(self.app.db,self.name.get_text(),self.profile());self.reload_profiles();self.message.set_text('✓ '+self.app.t('done'))

    def delete_profile(self):
        index=self.saved.get_selected()
        if index>=len(self.names):raise ValueError('L012: '+self.app.t('profile_missing'))
        tips.delete_profile(self.app.db,self.game,self.names[index]);self.reload_profiles();self.message.set_text('✓ '+self.app.t('done'))

    def generate(self):
        if self.app.busy:return
        count=int(self.count.get_text());profile=self.profile()
        self.cancel=threading.Event();self.run.set_sensitive(False);self.message.set_text('')
        self.progress.set_fraction(0)
        def progress(a,b):GLib.idle_add(self.progress.set_fraction,a/b)
        def done(batch):
            self.run.set_sensitive(True);self.batch=batch;self.show_batch(batch)
            self.message.set_text('✓ '+self.app.t('done'))
        def failed(message):self.run.set_sensitive(True);self.message.set_text(message)
        self.app.background(lambda:tips.create_batch(self.app.db,self.game,count,profile,self.app.config.get('max_tips',10000),cancel=self.cancel,progress=progress),done,True,failed)

    def show_batch(self,batch):
        self.batch=batch
        self.result.add_css_class('section-panel')
        while child:=self.result.get_first_child():self.result.remove(child)
        self.app.label(f"#{batch['id']} · {batch['count']} · {batch['rng_mode']}",self.result)
        controls=Gtk.Box(spacing=8);self.result.append(controls)
        save=Gtk.Button(label=self.app.t('tip_save'));controls.append(save)
        save.connect('clicked',lambda *_:self.app.guard(self.export))
        button=Gtk.Button(label=self.app.t('tip_print'));controls.append(button)
        button.connect('clicked',lambda *_:self.app.guard(lambda:exports.print_batch(batch,self.app.window,self.app.config['language'])))
        # Seitenweise Darstellung verhindert tausende GTK-Widgets bei großen Serien.
        self.page=0
        nav=Gtk.Box(spacing=8);self.result.append(nav)
        prev=Gtk.Button(label=self.app.t('previous_page'));nxt=Gtk.Button(label=self.app.t('next_page'));nav.append(prev);nav.append(nxt)
        label=Gtk.Label();nav.append(label);table=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);self.result.append(table)
        def display(page):
            self.page=max(0,min(page,(len(batch['tips'])-1)//100))
            while child:=table.get_first_child():table.remove(child)
            offset=self.page*100
            self.app.grid(['#',self.app.t('combination')],[(i,value) for i,value in enumerate(batch['tips'][offset:offset+100],offset+1)],table)
            label.set_text(f'{self.page+1} / {(len(batch["tips"])+99)//100}')
            prev.set_sensitive(self.page>0);nxt.set_sensitive(offset+100<len(batch['tips']))
        prev.connect('clicked',lambda *_:display(self.page-1));nxt.connect('clicked',lambda *_:display(self.page+1));display(0)


    def history(self):
        batches=tips.list_batches(self.app.db,self.game)
        if not batches:self.app.label(self.app.t('empty'));return
        row=Gtk.Box(spacing=8);self.app.content.append(row)
        dropdown=Gtk.DropDown.new_from_strings([f"#{b['id']} · {format_timestamp(b['created'])} · {b['count']} · {b['rng_mode']}" for b in batches]);row.append(dropdown)
        self.result=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);self.app.content.append(self.result)
        def load(*_):self.app.guard(lambda:self.show_batch(tips.get_batch(self.app.db,batches[dropdown.get_selected()]['id'])))
        dropdown.connect('notify::selected',load);load()

    def export(self):
        if not self.batch:raise ValueError('L012: '+self.app.t('tip_select_batch'))
        batch=self.batch
        self.app.save_file(f"{self.game}_tipps_{batch['id']}.csv",
                           lambda path:exports.export_batch(batch,path,self.app.config['language']))
