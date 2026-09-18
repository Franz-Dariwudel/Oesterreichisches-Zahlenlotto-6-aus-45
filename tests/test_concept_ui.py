"""GTK-Integration: Generator, Profile, Diagramme und Quellenfelder."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,tempfile,time,unittest
from uuid import uuid4
from lotto45.database import connect,ingest
try:
    from lotto45.app import App,Gtk,GLib
except ImportError:App=None

class ConceptUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if App is None or not Gtk.init_check():raise unittest.SkipTest('GTK-4-Anzeige erforderlich')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.db=self.root/'archive.sqlite3'
        draws=[{'spiel':'lotto','datum':'2026-09-13','zahlen':[1,2,3,4,5,6],'zusatzzahl':7},
               {'spiel':'joker','datum':'2026-09-13','nummer':'001100'}]
        with closing(connect(self.db)) as con:ingest(con,json.dumps(draws).encode(),'fixture',draws)
        with patch('lotto45.settings.load',return_value={'language':'de','max_tips':100,'repository':''}):self.app=App(self.db)
        self.app.set_application_id('eu.dogtruck.lotto45.test'+uuid4().hex);self.app.register(None);self.app.activate();self.addCleanup(self.close)
    def close(self):
        self.app.cancel_searches()
        if getattr(self.app,'statistics_view',None):self.app.statistics_view.close()
        for window in self.app.get_windows():window.destroy()
        self.app.quit()
    def wait(self,condition):
        deadline=time.monotonic()+10
        while not condition():
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            if time.monotonic()>deadline:self.fail('GTK-Zeitüberschreitung')
            time.sleep(.01)
    def test_inventory_tabs_and_source_pages_keep_edits(self):
        self.app.status()
        self.assertEqual(self.app.inventory_tabs.get_n_pages(),3)
        self.assertEqual(self.app.page_scroll.get_policy()[1],Gtk.PolicyType.NEVER)
        self.app.download_preferences()
        editor=self.app.source_editor
        first=editor['rows'][0]
        first['name'].set_text('Ungespeicherte Änderung')
        editor['add'].emit('clicked')
        self.assertTrue(editor['rows'][-1]['row'].get_visible())
        self.assertFalse(first['row'].get_visible())
        while editor['previous'].get_sensitive():editor['previous'].emit('clicked')
        self.assertTrue(first['row'].get_visible())
        self.assertEqual(first['name'].get_text(),'Ungespeicherte Änderung')
        self.app.source_dialog.close()

    def test_language_selection_downloads_matching_help_automatically(self):
        import shutil,threading
        from lotto45 import settings
        root=self.root/'language-editor';(root/'languages').mkdir(parents=True);(root/'help').mkdir();(root/'resources').mkdir()
        for code in ('de','en'):
            shutil.copy2(settings.ROOT/'languages'/f'{code}.json',root/'languages'/f'{code}.json')
            shutil.copy2(settings.ROOT/'help'/f'{code}.html',root/'help'/f'{code}.html')
        shutil.copytree(settings.ROOT/'help/images',root/'help/images')
        (root/'resources/language-index.json').write_text(json.dumps({'languages':['de','en','fr'],'names':{'fr':'Français'}}))
        release=threading.Event();calls=[]
        def download(repository,code,root):
            calls.append(code);release.wait(5)
            shutil.copy2(settings.ROOT/'languages'/f'{code}.json',root/'languages'/f'{code}.json')
            shutil.copy2(settings.ROOT/'help'/f'{code}.html',root/'help'/f'{code}.html')
        with patch('lotto45.app.ROOT',root),patch('lotto45.settings.download',side_effect=download):
            self.app.preferences();editor=self.app.preferences_editor
            try:
                editor['language'].set_selected(editor['codes'].index('fr'))
                self.wait(lambda:bool(calls));self.assertFalse(editor['save'].get_sensitive())
                release.set();self.wait(lambda:editor['save'].get_sensitive())
                self.assertEqual(calls,['fr']);self.assertTrue((root/'help/fr.html').exists())
                with patch('lotto45.settings.save') as save,patch.object(self.app,'rebuild'):
                    editor['save'].emit('clicked')
                    self.assertEqual(save.call_args[0][0]['language'],'fr')
            finally:release.set();editor['window'].close()

    def test_combined_check_action(self):
        from lotto45.services import update_check_report
        self.assertIsNone(self.app.lookup_action('probe-sources'))
        self.assertIsNone(self.app.lookup_action('db-check'))
        self.assertIsNone(self.app.lookup_action('diagnose'))
        def combined(path,sources,report_dir,**kwargs):
            return update_check_report(path,[],self.root/'reports',**kwargs)
        with patch('lotto45.archive_download.download_selected',return_value={'files':[], 'errors':[]}), patch('lotto45.services.update_check_report',side_effect=combined):
            self.app.lookup_action('check-data').activate(None)
            self.wait(lambda:not self.app.busy)
        self.assertEqual(len(self.app.check_steps),4)
        self.assertIn('Abgeschlossen',self.app.check_steps['probe_sources'].get_text())
        self.assertIn('Datenbankprüfung erfolgreich',self.app.notice.get_text())
        self.assertIn('Diagnosebericht gespeichert',self.app.notice.get_text())
        self.assertEqual(len(list((self.root/'reports').glob('*.json'))),1)

    def test_tip_profile_batch_and_history(self):
        self.app.lookup_action('joker-tip-create').activate(None);view=self.app.tip_view
        view.count.set_text('12');view.name.set_text('Mein Profil');view.save_profile()
        view.generate();self.wait(lambda:not self.app.busy)
        self.assertEqual(len(view.batch['tips']),12);self.assertTrue(all(len(v)==6 for v in view.batch['tips']))
        self.app.lookup_action('joker-tip-history').activate(None)
        self.assertEqual(len(self.app.tip_view.batch['tips']),12)
        self.assertEqual(self.app.tip_view.batch['game'],'joker')
    def test_chart_filters_and_sources(self):
        try:import matplotlib
        except ImportError:raise unittest.SkipTest('Matplotlib benötigt')
        self.app.lookup_action('joker-analysis-patterns').activate(None)
        self.wait(lambda:self.app.statistics_view.analysis is not None)
        view=self.app.statistics_view;self.assertIn('Joker',view.scope.get_text());view.pattern_chart()
        self.assertIsNotNone(view.chart.ax)
        for action in ('lotto-draw-export','joker-draw-export','stat-csv','stat-png','stat-pdf','stat-export'):
            self.assertIsNone(self.app.lookup_action(action))
        view.period_fields['from'].set_text('2030-01-01');view.reload()
        self.wait(lambda:view.analysis is not None);self.assertEqual(view.analysis.n,0)
        self.app.download_preferences();self.assertTrue(self.app.source_editor['rows'])
        for row in self.app.source_editor['rows']:self.assertIn('priority',row);self.assertIn('game',row);self.assertIn('format',row)
        self.app.source_dialog.destroy()

    def test_kind_column_tracks_whole_archive_for_both_games(self):
        for game,kind in [('lotto','draws'),('joker','joker')]:
            self.app.lookup_action(game+'-analysis-'+kind).activate(None)
            view=self.app.statistics_view;self.wait(lambda:view.analysis is not None)
            index=next(i for i,t in enumerate(view.report['tables']) if any(fmt=='kind' for _,fmt in t.columns))
            view.section.set_selected(index);view.select_table()
            kind_index=next(i for i,(_,fmt) in enumerate(view.table.columns) if fmt=='kind')
            self.assertNotIn(kind_index,view.visible_columns)
            self.assertFalse(view.kind_cell.get_visible())
            self.assertFalse(view.rule_editor.kind_cell.get_visible())
            expected=view.visible_columns[1]
            view.scroll.get_child().headers[1].emit("clicked")
            self.assertEqual(view.sort_column,expected)
            record={'spiel':game,'datum':'2026-09-16','kennung':'zusatz'}
            record.update({'zahlen':[2,3,4,5,6,7],'zusatzzahl':8} if game=='lotto' else {'nummer':'002200'})
            with closing(connect(self.db)) as con:ingest(con,json.dumps([record]).encode(),'fixture:'+game,[record])
            # Die weitere Kennung liegt außerhalb des sichtbaren Zeitraums.
            view.period_fields['to'].set_text('2026-09-13');view.reload()
            self.wait(lambda:view.analysis is not None)
            view.section.set_selected(index);view.select_table()
            self.assertIn(kind_index,view.visible_columns)
            self.assertTrue(view.kind_cell.get_visible())
            self.assertTrue(view.rule_editor.kind_cell.get_visible())
            self.assertEqual(view.analysis.n,1)

    def test_rule_settings_persist_and_checkboxes_apply_only_selected_values(self):
        from lotto45 import rule_settings,tips
        with patch('lotto45.settings.ROOT',self.root):
            self.app.lookup_action('lotto-analysis-sums').activate(None)
            view=self.app.statistics_view;self.wait(lambda:view.analysis is not None)
            editor=view.rule_editor;editor.fields['sum'].set_text('100,120');editor.save()
            saved=json.loads((self.root/'config/settings.json').read_text())
            self.assertEqual(rule_settings.load(saved,'lotto')['rules']['sum'],[100,120])
            self.assertEqual(rule_settings.load(saved,'joker')['rules']['sum'],[15,40])
            self.app.lookup_action('lotto-tip-create').activate(None);form=self.app.tip_view
            self.assertEqual(form.entries,{})
            form.mode.set_selected(1)
            self.assertEqual(form.profile()['rules'],{})
            form.checks['sum'].set_active(True)
            self.assertEqual(form.profile()['rules'],{'sum':[100,120]})
            values,_=tips.generate('lotto',5,form.profile(),seed=42)
            self.assertTrue(all(100<=sum(v)<=120 for v in values))
            form.name.set_text('Grenzen');form.save_profile()
            # Andere aktuelle Werte ändern den gespeicherten Profilstand nicht.
            p=rule_settings.load(self.app.config,'lotto');p['rules']['sum']=[130,150]
            rule_settings.save(self.app,'lotto',p)
            form.load_profile()
            self.assertEqual(form.profile()['rules']['sum'],[100,120])
            self.assertEqual(rule_settings.load(self.app.config,'lotto')['rules']['sum'],[100,120])
            form.checks['sum'].set_active(False);self.assertEqual(form.profile()['rules'],{})
            form.mode.set_selected(0);self.assertEqual(form.profile()['weight'],0)

    def test_invalid_rule_values_and_failed_save_preserve_settings(self):
        from lotto45 import rule_settings
        with patch('lotto45.settings.ROOT',self.root):
            self.app.lookup_action('joker-analysis-patterns').activate(None)
            view=self.app.statistics_view;self.wait(lambda:view.analysis is not None)
            editor=view.rule_editor;editor.fields['sum'].set_text('10,30');editor.save()
            before=(self.root/'config/settings.json').read_bytes()
            editor.fields['sum'].set_text('40,10')
            with self.assertRaises(ValueError):editor.save()
            self.assertEqual((self.root/'config/settings.json').read_bytes(),before)
            editor.fields['sum'].set_text('20,40')
            with patch('lotto45.settings.save',side_effect=OSError('read only')):
                with self.assertRaisesRegex(ValueError,'L004'):editor.save()
            self.assertEqual(rule_settings.load(self.app.config,'joker')['rules']['sum'],[10,30])
            self.assertEqual((self.root/'config/settings.json').read_bytes(),before)

    def test_calendar_and_german_date_filters(self):
        from lotto45 import rule_settings
        with patch('lotto45.settings.ROOT',self.root):
            self.app.lookup_action('lotto-analysis-sums').activate(None)
            view=self.app.statistics_view;self.wait(lambda:view.analysis is not None)
            view.period_fields['from'].set_text('11.1.2000')
            view.period_fields['to'].set_text('1.12.2026');view.reload()
            self.wait(lambda:view.analysis is not None);self.assertEqual(view.analysis.n,1)
            field=view.rule_editor.scope_fields['from']
            field.calendar.select_day(GLib.DateTime.new_local(2020,2,29,12,0,0))
            field.calendar.emit('day-selected')
            self.assertEqual(field.get_text(),'29.02.2020')
            view.rule_editor.save()
            self.assertEqual(rule_settings.load(self.app.config,'lotto')['from'],'2020-02-29')
            field.set_text('29.2.2021')
            with self.assertRaises(ValueError):view.rule_editor.save()
            self.assertFalse(field.get_hexpand());self.assertEqual(field.get_max_width_chars(),10)
            self.app.lookup_action('history').activate(None)
            self.assertTrue(hasattr(self.app.history_controls['entry'],'calendar'))

    def test_draw_kind_filters_hidden_until_other_kind_imported(self):
        for game in ('lotto','joker'):
            self.app.game=game
            self.app.history();self.assertFalse(self.app.history_controls['kind'].get_visible())
            self.app.quotes();self.assertFalse(self.app.quotes_view.kind_entry.get_visible())
            record={'spiel':game,'datum':'2026-09-16','kennung':'zusatz'}
            record.update({'zahlen':[2,3,4,5,6,7],'zusatzzahl':8} if game=='lotto' else {'nummer':'002200'})
            with closing(connect(self.db)) as con:ingest(con,json.dumps([record]).encode(),'fixture:'+game,[record])
            self.app.history();self.assertTrue(self.app.history_controls['kind'].get_visible())
            self.app.quotes();self.assertTrue(self.app.quotes_view.kind_entry.get_visible())

    def test_frequency_chart_displays_exact_maximum_after_refresh(self):
        from lotto45.plotting import Chart
        data={'kind':'frequency','type':'bar','count':1000,'labels':['01','02'],
              'values':[552,500],'x_title':'s_number','y_title':'s_hits'}
        chart=Chart(data,self.app.t,lambda value,kind:str(value))
        self.addCleanup(chart.close)
        for maximum in (552,601,1000,3,0):
            data['values']=[maximum,0];chart.render()
            self.assertIn(maximum,chart.ax.get_yticks())
            self.assertIn('Maximale Anzahl: '+str(maximum),chart.ax.get_title())
            self.assertGreater(chart.ax.get_ylim()[1],maximum)
        data['count']=0;data['values']=[];chart.render()
        self.assertNotIn('Maximale Anzahl:',chart.ax.get_title())

    def test_all_chart_types_show_data_maximum_without_clipping_references(self):
        from lotto45.plotting import Chart
        base={'kind':'test','count':3,'x_title':'s_number','y_title':'s_hits'}
        datasets=[dict(base,type='line',labels=['a','b','c'],values=[-3.5,-1.25,-2],reference=[2,2,2]),
                  dict(base,type='bar',labels=['a','b','c'],values=[0,8,8]),
                  dict(base,type='heatmap',matrix=[[None,12],[12,3]])]
        for data in datasets:
            chart=Chart(data,self.app.t,lambda value,kind:str(value));self.addCleanup(chart.close)
            maximum=12 if data['type']=='heatmap' else max(data['values'])
            self.assertEqual(chart.maximum,maximum)
            self.assertIn('Maximum: '+str(maximum),chart.ax.get_title())
            axis=chart.figure.axes[1] if data['type']=='heatmap' else chart.ax
            self.assertIn(maximum,axis.get_yticks())
            if data['type']=='line':
                self.assertLess(chart.ax.get_ylim()[0],-3.5)
                self.assertGreater(chart.ax.get_ylim()[1],2)
            chart.render();self.assertEqual(len(chart.figure.axes),2 if data['type']=='heatmap' else 1)

    def test_pair_matrix_shows_all_45_axis_labels(self):
        from lotto45.plotting import Chart
        from lotto45.statistics import Analysis,load_draws
        data=Analysis(load_draws(self.db),0).chart('heatmap')
        chart=Chart(data,self.app.t,lambda value,kind:str(value));self.addCleanup(chart.close)
        self.assertEqual([t.get_text() for t in chart.ax.get_xticklabels()],[f'{n:02d}' for n in range(1,46)])
        self.assertEqual([t.get_text() for t in chart.ax.get_yticklabels()],[f'{n:02d}' for n in range(1,46)])
        self.assertEqual(chart.ax.images[0].get_array().shape,(45,45))
        self.assertEqual(chart.ax.get_aspect(),1)
        self.assertEqual(chart.ax.get_xlim(),(-.5,44.5))
        self.assertEqual(chart.ax.get_ylim(),(44.5,-.5))
