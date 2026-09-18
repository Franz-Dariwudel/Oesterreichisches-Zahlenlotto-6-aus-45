"""Einheitliche Datumsanzeige; gespeicherte ISO-Daten und Sortierschlüssel bleiben erhalten."""
import re
import datetime


LANGUAGE="de"
# Sprachkürzel entsprechen den dynamisch geladenen Oberflächenkatalogen.
WEEKDAYS={
    'de':('Mo.','Di.','Mi.','Do.','Fr.','Sa.','So.'),
    'en':('Mon','Tue','Wed','Thu','Fri','Sat','Sun'),
    'es':('lun.','mar.','mié.','jue.','vie.','sáb.','dom.'),
    'fr':('lun.','mar.','mer.','jeu.','ven.','sam.','dim.'),
    'pt':('seg.','ter.','qua.','qui.','sex.','sáb.','dom.'),
    'zh':('周一','周二','周三','周四','周五','周六','周日'),
    'hi':('सोम','मंगल','बुध','गुरु','शुक्र','शनि','रवि'),
    'ar':('الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد'),
    'ru':('пн','вт','ср','чт','пт','сб','вс'),
    'tr':('Pzt','Sal','Çar','Per','Cum','Cmt','Paz'),
}

def format_date(value,weekday=True):
    """ISO-Datum am Textanfang formatieren, etwa auch vor einer Ziehungskennung."""
    if not value:return '—'
    if re.fullmatch(r'\d{4}-\d{2}',str(value)):return str(value)[5:7]+'.'+str(value)[:4]
    def replace(match):
        try:date=datetime.date.fromisoformat(match.group(0))
        except ValueError:return match.group(0)
        day=WEEKDAYS.get(LANGUAGE,WEEKDAYS['en'])[date.weekday()]
        if not weekday:return date.strftime('%d.%m.%Y')
        return day+' '+date.strftime('%d.%m.%Y')
    return re.sub(r'^\d{4}-\d{2}-\d{2}(?=$|\D)',replace,str(value))


def format_log_dates(text):
    """Auch alte Protokoll-Zeitstempel lesbar anzeigen, ohne die Datei zu verändern."""
    return re.sub(r'(?m)^(\d{4})-(\d{2})-(\d{2})(?=\s\d{2}:)',r'\3.\2.\1',text)


def format_timestamp(value):
    """Gespeicherte UTC-Zeit in der lokalen Zeitzone samt Wochentag anzeigen."""
    if not value:return '—'
    try:
        parsed=datetime.datetime.fromisoformat(value).astimezone()
        return format_date(parsed.date().isoformat())+' '+parsed.strftime('%H:%M:%S %Z')
    except (ValueError,TypeError,OverflowError):return str(value)


def parse_input_date(value):
    """Deutsche Tag.Monat.Jahr-Eingabe oder ISO prüfen und als ISO liefern."""
    value=value.strip()
    if not value:return ''
    match=re.fullmatch(r'(\d{1,2})\.(\d{1,2})\.(\d{4})',value)
    if match:
        day,month,year=map(int,match.groups())
        return datetime.date(year,month,day).isoformat()
    return datetime.date.fromisoformat(value).isoformat()
