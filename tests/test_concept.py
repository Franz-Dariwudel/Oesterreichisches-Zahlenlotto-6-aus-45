"""Konzept-Regressionen: Serien, Regeln, Migration und sichere Temp-Dienste."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json
import sqlite3
import tempfile
import threading
import unittest
from lotto45 import tips,patterns,settings,services,tempwork,exports
from lotto45.database import connect,ingest,SCHEMA
from lotto45.archive_download import download_selected,probe_sources
from lotto45.statistics import Draw


class GeneratorTests(unittest.TestCase):
    def test_random_unique_valid_and_reproducible(self):
        for game in ('lotto','joker'):
            a,p=tips.generate(game,300,seed=7);b,_=tips.generate(game,300,seed=7)
            self.assertEqual(a,b);self.assertEqual(len(set(a)),300)
            if game=='lotto':
                for value in a:self.assertEqual(tuple(sorted(set(value))),value);self.assertEqual(len(value),6);self.assertTrue(1<=min(value)<max(value)<=45)
            else:
                self.assertTrue(all(len(v)==6 and v.isdigit() for v in a));self.assertTrue(any(v[0]=='0' for v in a))

    def test_system_random_default(self):
        with patch('lotto45.tips.secrets.SystemRandom',wraps=tips.secrets.SystemRandom) as rng:
            tips.generate('lotto',2);rng.assert_called_once()

    def test_random_ignores_filters_and_history(self):
        p=tips.default_profile('lotto');p['rules']={'even':[6,6],'low':[0,0],'quantiles':[0,0]};p['weight']=5
        self.assertEqual(tips.generate('lotto',20,p,seed=8)[0],tips.generate('lotto',20,seed=8)[0])

    def test_lotto_rules_enforced(self):
        p=tips.default_profile('lotto');p.update(mode='filtered',rules={'sum':[110,180],'even':[2,4],'low':[2,4],'span':25,'run':2,'prime':[1,3],'birthday':[2,5]})
        values,_=tips.generate('lotto',50,p,seed=19)
        for ns in values:
            self.assertTrue(110<=sum(ns)<=180);self.assertTrue(2<=sum(n%2==0 for n in ns)<=4)
            self.assertGreaterEqual(ns[-1]-ns[0],25);self.assertLessEqual(tips.lotto_run(ns),2)

    def test_joker_rules_and_leading_zeros(self):
        p=tips.default_profile('joker');p.update(mode='filtered',rules={'sum':[5,30],'different':[3,5],'run':1,'palindrome':'avoid'})
        values,_=tips.generate('joker',30,p,seed=1)
        for value in values:
            self.assertNotEqual(value,value[::-1]);self.assertTrue(3<=len(set(value))<=5)
            self.assertTrue(all(a!=b for a,b in zip(value,value[1:])))

    def test_blocking_rules_bounded_no_partial_batch(self):
        p=tips.default_profile('lotto');p.update(mode='filtered',rules={'even':[6,6],'sum':[21,21]})
        with self.assertRaisesRegex(ValueError,'Blockierende Regeln'):tips.generate('lotto',2,p,seed=1,max_attempts=100)
        stop=threading.Event();stop.set()
        with self.assertRaises(InterruptedError):tips.generate('joker',10,cancel=stop)

    def test_limits_profile_validation(self):
        for count in (0,-1,1.2,True,10001):
            with self.assertRaises(ValueError):tips.generate('lotto',count)
        for changes in ({'weight':float('nan')},{'weekday':7},{'from':'2026-02-30'},{'rules':{'nope':1}},{'rules':{'sum':[255,21]}}):
            with self.assertRaises(ValueError):tips.validate({**tips.default_profile('lotto'),**changes})

    def test_history_filter_and_quantiles(self):
        draws=[Draw(1,'2026-09-13','haupt',(1,2,3,4,5,6),7),Draw(2,'2026-09-16','bonus',(10,20,30,31,32,40),7)]
        p=tips.default_profile('lotto');p.update(mode='filtered',weekday=6,last=1)
        self.assertEqual(tips.select_draws(draws,p),draws[:1])
        p.update(weekday=-1,rules={'quantiles':[0,100],'repeat':2})
        values,_=tips.generate('lotto',10,p,draws,seed=4)
        self.assertTrue(all(len(set(v)&set(draws[-1].numbers))<=2 for v in values))
        with self.assertRaisesRegex(ValueError,'Keine Ziehungen'):tips.generate('lotto',10,p,[],seed=4)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'draws.sqlite3'
        self.records=[{'spiel':'joker','datum':'2026-09-13','nummer':'001234'},
                      {'spiel':'lotto','datum':'2026-09-13','zahlen':[1,2,3,4,5,6],'zusatzzahl':7}]
        with closing(connect(self.db)) as con:ingest(con,json.dumps(self.records).encode(),'test',self.records)

    def test_profiles_batches_snapshot(self):
        profile=tips.default_profile('joker');tips.save_profile(self.db,'Test',profile)
        self.assertEqual(tips.selected_profile(self.db,'joker'),{**profile,'name':'Test'})
        batch=tips.create_batch(self.db,'joker',40,profile,seed=7)
        profile['mode']='filtered';tips.save_profile(self.db,'Test',profile)
        self.assertEqual(tips.get_batch(self.db,batch['id'])['profile']['mode'],'random')
        self.assertEqual(len(tips.list_batches(self.db,'joker')),1);self.assertEqual(tips.list_batches(self.db,'lotto'),[])
        path=self.root/'tips.csv';exports.export_batch(batch,path)
        self.assertIn(batch['tips'][0],path.read_text())
        with self.assertRaises(ValueError):exports.export_batch(batch,self.root/'tips.pdf')
        tips.delete_profile(self.db,'joker','Test')
        with self.assertRaises(ValueError):tips.selected_profile(self.db,'joker')
        self.assertEqual(len(tips.get_batch(self.db,batch['id'])['tips']),40)

    def test_failed_or_cancelled_generation_saves_nothing(self):
        p=tips.default_profile('joker');p.update(mode='filtered',rules={'sum':[54,54],'different':[6,6]})
        with self.assertRaises(ValueError):tips.create_batch(self.db,'joker',2,p,seed=1)
        self.assertEqual(tips.list_batches(self.db,'joker'),[])

    def test_migration_backup_preserves_original_draws(self):
        legacy=self.root/'old.sqlite3'
        with closing(sqlite3.connect(legacy)) as con:
            con.executescript(SCHEMA);con.execute("INSERT INTO joker_tipps VALUES('000001')")
            con.execute("INSERT INTO joker_ziehungen(datum,nummer) VALUES('2026-09-13','000001')");con.commit()
        with closing(connect(legacy)) as con:
            self.assertEqual(con.execute('SELECT nummer FROM joker_ziehungen').fetchone()[0],'000001')
            self.assertEqual(con.execute("SELECT value FROM metadata WHERE key='extension_version'").fetchone()[0],'1')
        backups=list((self.root/'backups').glob('*.sqlite3'));self.assertEqual(len(backups),1)
        with closing(connect(backups[0],create=False)) as con:self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master WHERE name='tip_batch'").fetchone())
        with closing(connect(legacy)):pass
        self.assertEqual(len(list((self.root/'backups').glob('*.sqlite3'))),1)

    def test_backup_and_diagnosis(self):
        target=self.root/'backup.sqlite3';services.backup(self.db,target)
        self.assertEqual(services.check(target)['integrity'],['ok'])
        with self.assertRaises(ValueError):services.backup(self.db,target)
        report=services.diagnose(self.db);self.assertNotIn(str(self.root),json.dumps(report))

    def test_import_log_duplicate_and_error(self):
        source=[{'name':'Test','url':'https://example.org/draws.json','enabled':True}]
        raw=json.dumps([{'spiel':'joker','datum':'2026-09-16','nummer':'000123'}]).encode()
        for _ in range(2):download_selected(source,self.db,self.root,fetch=lambda u:raw)
        self.assertEqual({r['status'] for r in services.import_log(self.db)},{'success','unchanged'})
        result=download_selected(source,self.db,self.root,fetch=lambda u:b'invalid')
        self.assertTrue(result['errors']);self.assertEqual(services.import_log(self.db)[0]['status'],'error')
        self.assertFalse(list(self.root.glob('lotto_joker_*')))
        self.assertEqual(probe_sources(source,fetch=lambda u:raw)[0]['status'],'OK')

    def test_temp_cleanup_preserves_active_and_foreign(self):
        foreign=self.root/'lotto_joker_foreign';foreign.mkdir();(foreign/'data').write_text('keep')
        with tempwork.workspace(self.root) as active:
            self.assertEqual(tempwork.cleanup(self.root),[]);self.assertTrue(active.exists())
        stale=self.root/'lotto_joker_stale';stale.mkdir();(stale/'.owner').write_text(tempwork.MARKER);(stale/'.lock').touch()
        self.assertEqual(tempwork.cleanup(self.root),[str(stale)]);self.assertTrue(foreign.exists())

    def test_config_recovery_preserves_broken_file(self):
        (self.root/'config').mkdir();path=self.root/'config/settings.json';path.write_text('{bad')
        config=settings.load(self.root)
        self.assertEqual(config['max_tips'],10000);self.assertTrue(list(path.parent.glob('*.broken')))

    def test_patterns_exact_values(self):
        report=patterns.analyse([(1,'2026-09-13','haupt','001100')],'joker')
        self.assertEqual(report['series']['sum'][2],1)
        self.assertEqual(report['series']['run'][2],1)
        self.assertEqual(report['series']['symmetry'][3],1)
        self.assertEqual(report['positions'][0][0],1)
        self.assertEqual(sum(map(sum,report['transitions'])),5)
        self.assertEqual(sum(map(sum,report['weekdays'])),6)


if __name__=='__main__':unittest.main()
