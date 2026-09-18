"""Historisches Joker-Archiv vollständig abfragen, validieren und verlustfrei ergänzen."""
from contextlib import closing
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from lotto45 import joker_history as history
from lotto45.archive_download import discover_archives,download_selected
from lotto45.database import connect,ingest


def page(rows,count=None):
    body=''.join('<tr>'+''.join('<td>'+str(cell)+'</td>' for cell in row)+'</tr>' for row in rows)
    return ('<html><p>Das Archiv umfasst alle Gewinnzahlen von der 1. Ziehung bis zur <span>'
            +str(len(rows) if count is None else count)+'. Ziehung</span>.</p>'
            '<table><tr><th>Ziehungsdatum</th><th colspan="6">Jokerzahl</th></tr>'+body+'</table></html>').encode()


class JokerHistoryTests(unittest.TestCase):
    def test_official_page_adds_unlisted_years_and_preserves_current_url(self):
        raw=b'<a href="https://statics.win2day.at/media/NN_W2D_STAT_Joker_2023.csv?v=1">CSV</a>'
        found=discover_archives(raw,'https://www.win2day.at/lotterie/joker-statistik')
        self.assertEqual(len(found),7)
        self.assertTrue(found[0].endswith('2017.csv'));self.assertTrue(found[-1].endswith('2023.csv?v=1'))
        self.assertEqual(len(discover_archives(raw,'https://example.org/archive')),1)

    def test_dates_and_leading_zeros(self):
        records,issues=history.parse_archive(page([['Sonntag, 02. Oktober 1988',*'001073'],['Sonntag, 09. Oktober 1988',*'169713']]))
        self.assertFalse(issues);self.assertEqual(records[0]['datum'],'1988-10-02')
        self.assertEqual(records[0]['nummer'],'001073');self.assertNotIn('quoten',records[0])

    def test_short_default_view_is_not_silently_imported_as_full_archive(self):
        with self.assertRaisesRegex(ValueError,'unvollständig'):
            history.parse_archive(page([['Sonntag, 02. Oktober 1988',*'261073']],count=3570))
        with self.assertRaisesRegex(ValueError,'Archivkopf'):history.parse_archive(b'<html>error</html>')

    def test_invalid_rows_and_ambiguous_duplicate_dates_are_not_imported(self):
        raw=page([['Sonntag, 02. Oktober 1988',*'261073'],['Sonntag, 09. Oktober 1988',*'169713'],
                  ['Sonntag, 09. Oktober 1988',*'123456'],['Montag, 16. Oktober 1988',*'333333'],
                  ['Sonntag, 23. Oktober 1988',*'12345x']])
        records,issues=history.parse_archive(raw)
        self.assertEqual(len(records),1);self.assertEqual(len(issues),4)
        self.assertTrue(all(i[1].startswith('L003') for i in issues))

    def test_existing_official_data_quotes_and_raw_bytes_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);db=root/'lotto.sqlite3';downloads=root/'Downloads';downloads.mkdir();(downloads/'keep.txt').write_text('keep')
            original={'spiel':'joker','datum':'2026-09-13','nummer':'238894',
                      'quoten':[{'klasse':'1','regelwerk':'test','gewinner':2,'waehrung':'EUR','betrag_hundertstel':18607440}]}
            with closing(connect(db)) as con:ingest(con,json.dumps([original]).encode(),'official',[original])
            raw=page([['Sonntag, 02. Oktober 1988',*'261073'],['Sonntag, 13. September 2026',*'999999']])
            sources=[{'name':'History','url':history.URL,'enabled':True}]
            result=download_selected(sources,db,downloads,lambda _:raw)
            self.assertFalse(result['errors']);self.assertEqual(result['files'][0]['konflikte'],1)
            with closing(connect(db,create=False)) as con:
                self.assertEqual(dict(con.execute('SELECT datum,nummer FROM joker_ziehungen')),{'1988-10-02':'261073','2026-09-13':'238894'})
                self.assertEqual(con.execute('SELECT betrag_hundertstel FROM joker_quoten').fetchone()[0],18607440)
                self.assertEqual(con.execute('SELECT original FROM import_quellen WHERE uri=?',(history.URL,)).fetchone()[0],raw)
            # Die Uhr bzw. das Abrufdatum im HTML darf keine zweite Quelle erzeugen.
            second=download_selected(sources,db,downloads,lambda _:raw.replace(b'<html>',b'<html><p>Serverzeit 19:45:32</p>'))
            self.assertTrue(second['files'][0]['bereits_importiert'])
            with closing(connect(db,create=False)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM import_quellen').fetchone()[0],2)
            self.assertEqual([p.name for p in downloads.iterdir()],['keep.txt'])

    def test_form_requests_keep_session_cookies(self):
        # Ein lokaler HTTP-Server simuliert das öffentlich sichtbare Sitzungsformular.
        seen=[];full=page([['Sonntag, 02. Oktober 1988',*'261073']])
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                if self.path=='/result':
                    seen.append(self.headers.get('Cookie'));raw=full
                else:
                    raw=('<form action="http://127.0.0.1:'+str(self.server.server_port)+'/search">'
                         '<input name="jokerziehungendatumbeginn" min="1988-10-02">'
                         '<input name="jokerziehungendatumende" max="2026-09-09"></form>').encode()
                self.send_response(200);self.send_header('Set-Cookie','archive=test; Path=/');self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                seen.append(parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode()))
                seen.append(self.headers.get('Cookie'))
                self.send_response(303);self.send_header('Location','/result');self.end_headers()
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.object(history,'is_url',return_value=True),patch.object(history,'FORM',base+'/search'):
                self.assertEqual(history.fetch_archive(base+'/start'),full)
            self.assertEqual(seen[0]['jokerziehungendatumbeginn'],['1988-10-02'])
            self.assertEqual(seen[0]['jokerziehungendatumende'],['2026-09-09'])
            self.assertEqual(seen[1:],['archive=test','archive=test'])
        finally:server.shutdown();server.server_close();thread.join()

    def test_changed_form_is_rejected(self):
        class Response:
            url=history.URL
            def read(self,_):return b'<form action="https://example.org/wrong"></form>'
            def __enter__(self):return self
            def __exit__(self,*_):pass
        class Opener:
            def open(self,*_,**__):return Response()
        with patch.object(history,'build_opener',return_value=Opener()):
            with self.assertRaisesRegex(ValueError,'formular'):history.fetch_archive(history.URL)
