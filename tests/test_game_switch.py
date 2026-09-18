"""Spielwechsel über echte GTK-Buttons: Ansicht, Zeitraum und Abfragen erhalten."""
from contextlib import closing
from pathlib import Path
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from lotto45.database import connect,ingest

try:
    from lotto45.app import App,Gtk,GLib
except ImportError:
    App=None


class GameSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if App is None or not Gtk.init_check():
            raise unittest.SkipTest('GTK 4 und eine grafische Anzeige erforderlich')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'draws.sqlite3'
        records=[]
        for date,numbers in [('2025-01-01',[1,2,3,4,5,6]),('2025-01-05',[7,8,9,10,11,12]),
                             ('2026-09-13',[1,2,3,4,5,6])]:
            records.extend([
                {'spiel':'lotto','datum':date,'zahlen':numbers,'zusatzzahl':45},
                {'spiel':'joker','datum':date,'nummer':'001234'}])
        with closing(connect(self.db)) as con:
            ingest(con,json.dumps(records).encode(),'test:game-switch',records)
        self.before=self.db.read_bytes()
        with patch('lotto45.settings.load',return_value={'language':'de'}):
            self.app=App(self.db)
        self.app.set_application_id('eu.dogtruck.lotto45.test'+uuid4().hex)
        self.app.register(None);self.app.activate()
        self.addCleanup(self.close_app)

    def close_app(self):
        self.app.cancel_searches()
        if getattr(self.app,'quotes_view',None):self.app.quotes_view.close()
        if getattr(self.app,'statistics_view',None):self.app.statistics_view.close()
        self.app.window.destroy();self.app.quit()

    def wait(self,predicate):
        end=time.monotonic()+5
        context=GLib.MainContext.default()
        while not predicate():
            if time.monotonic()>end:self.fail('Zeitüberschreitung bei der GTK-Suche')
            while context.pending():context.iteration(False)
            time.sleep(.005)

    def select(self,game,page):
        self.app.game_buttons[game].set_active(True)
        self.assertEqual(self.app.page_heading.get_text(),game.capitalize()+' · '+self.app.t(page))
        self.assertTrue(self.app.game_buttons[game].get_active())

    def results(self,dates):
        controls=self.app.history_controls
        self.wait(lambda:not self.app.search_timer and self.app.history_cancel is None)
        self.assertEqual({r['datum'] for r in controls['state']['rows']},set(dates))
        self.assertTrue(all(r['spiel']==self.app.game for r in controls['state']['rows']))

    def test_date_search_keeps_period_and_lotto_filter_in_both_directions(self):
        self.app.lookup_action('history').activate(None)
        self.app.history_controls['entry'].set_text('01.2025')
        self.app.history_controls['numbers'].set_text('1')
        self.results(['2025-01-01'])
        self.select('joker','history')
        self.assertEqual(self.app.history_controls['entry'].get_text(),'01.2025')
        self.results(['2025-01-01','2025-01-05'])
        self.assertFalse(self.app.history_controls['numbers'].get_parent().get_visible())
        # Auch eine bestätigte Joker-Suche darf den gemerkten Lotto-Filter nicht leeren.
        self.app.history_controls['search'].emit('clicked')
        self.results(['2025-01-01','2025-01-05'])
        self.select('lotto','history')
        self.assertEqual(self.app.history_controls['numbers'].get_text(),'1')
        self.results(['2025-01-01'])
        for period,dates in [('2025',['2025-01-01','2025-01-05']),('05.01.2025',['2025-01-05']),
                             ('1',['2025-01-01','2026-09-13'])]:
            self.app.history_controls['numbers'].set_text('')
            self.app.history_controls['entry'].set_text(period)
            # Wechsel während der Tipppause: alte Abfragen dürfen nicht nachträglich erscheinen.
            self.select('joker','history');self.results(dates)
            self.select('lotto','history');self.results(dates)
            self.assertEqual(self.app.history_controls['entry'].get_text(),period)
        self.assertEqual(self.db.read_bytes(),self.before)

    def test_empty_invalid_and_other_views_do_not_jump_to_stale_search(self):
        self.app.history()
        self.select('joker','history');self.select('lotto','history')
        self.assertEqual(self.app.history_controls['entry'].get_text(),'')
        self.assertIsNone(self.app.history_controls['scroll'].get_child())
        self.app.history_controls['entry'].set_text('31.02.2025')
        self.select('joker','history')
        self.wait(lambda:not self.app.search_timer and self.app.history_cancel is None)
        self.assertIn('L002',self.app.history_controls['status'].get_text())
        self.select('lotto','history')
        self.app.history_controls['entry'].set_text('2025')
        self.app.lookup_action('home').activate(None)
        self.select('joker','home');self.select('lotto','home')
        self.assertEqual(self.app.search_timer,0)
        self.assertIsNone(self.app.history_cancel)
        for page in ('lookup','quotes'):
            self.app.lookup_action(page).activate(None)
            self.select('joker',page);self.select('lotto',page)
        self.assertEqual(self.db.read_bytes(),self.before)


    def test_tips_and_history_keep_menu_in_both_directions(self):
        for history in (False,True):
            self.app.show_tips(history)
            for game in ('joker','lotto','joker','lotto'):
                self.select(game,'tip_history' if history else 'tip_create')
                self.assertEqual(self.app.current_view,'tip_history' if history else 'tips')
                self.assertEqual(self.app.tip_view.game,game)
                self.assertEqual(hasattr(self.app.tip_view,'count'),not history)
        self.assertEqual(self.db.read_bytes(),self.before)

    def test_statistics_keep_common_page_and_restore_lotto_specific_page(self):
        self.app.show_statistics('patterns')
        for game in ('joker','lotto'):
            self.select(game,'s_patterns')
            self.assertEqual(self.app.statistics_view.kind,'patterns')
            self.wait(lambda:self.app.statistics_view.analysis is not None)
        from lotto45.statistics import KINDS
        for kind in KINDS:
            self.app.show_statistics(kind)
            self.select('joker','s_joker')
            self.assertEqual(self.app.current_view,'statistics')
            self.select('lotto','s_'+kind)
            self.assertEqual(self.app.statistics_view.kind,kind)
        self.wait(lambda:self.app.statistics_view.analysis is not None)
        self.assertEqual(self.db.read_bytes(),self.before)


if __name__=='__main__':unittest.main()
