"""Paginierter Systemdruck von Tippserien und atomare Diagnosedateien.

Dateiausgaben werden neben dem Ziel vorbereitet und atomar ersetzt. Die
Datenbankhistorie bleibt unverändert. GTK wird ausschließlich beim Drucken geladen.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import csv
import json
import tempfile
from .date_display import format_date


@contextmanager
def atomic_target(path):
    path=Path(path);temporary=None
    try:
        fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',suffix=path.suffix,dir=path.parent)
        os.close(fd);temporary=Path(name)
        yield temporary
        temporary.replace(path)
    except Exception as error:
        raise ValueError(f'L014: {path}: {error}. Speicherort, Format und Schreibrechte prüfen.') from error
    finally:
        if temporary:temporary.unlink(missing_ok=True)


def batch_lines(batch,language='de'):
    de=language=='de'
    return [f"{batch['game'].capitalize()} · {'Tippserie' if de else 'Tip batch'} #{batch['id']}",
            format_date(batch['created'][:10])+' '+batch['created'][11:19]+' UTC',
            ('Anzahl' if de else 'Count')+f": {batch['count']} · {batch['rng_mode']}",
            ('Modus' if de else 'Mode')+': '+batch['profile']['mode']+(' · '+('Profil' if de else 'Profile')+': '+batch['profile']['name'] if batch['profile'].get('name') else ''),
            ('Vergangene Ziehungen erhöhen keine Gewinnchance.' if de else 'Past draws do not increase winning chances.'),'',
            *[f'{i:5d}.  {value}' for i,value in enumerate(batch['tips'],1)]]


def paint_page(cr,lines,width,height,page,pages):
    """Gemeinsamer Zeichner für PDF und GTK-Druck; 34 Tipps je Seite."""
    import gi
    gi.require_version('Pango','1.0')
    gi.require_version('PangoCairo','1.0')
    from gi.repository import Pango,PangoCairo
    cr.save()
    scale=min(width/595,height/842);cr.scale(scale,scale);width,height=595,842
    cr.set_source_rgb(0,0,0)
    y=20
    for i,text in enumerate(lines):
        layout=PangoCairo.create_layout(cr)
        PangoCairo.context_set_resolution(layout.get_context(),72)
        font=Pango.FontDescription('Sans 12' if i<6 else 'Monospace 11')
        layout.set_font_description(font);layout.set_width(int((width-40)*Pango.SCALE))
        layout.set_text(text,-1);cr.move_to(20,y);PangoCairo.show_layout(cr,layout)
        y+=max(16,layout.get_pixel_size()[1]+3)
    layout=PangoCairo.create_layout(cr);layout.set_text(f'{page+1} / {pages}',-1)
    cr.move_to(20,height-25);PangoCairo.show_layout(cr,layout)
    cr.restore()


def pages_for(batch,language):
    lines=batch_lines(batch,language);head=lines[:6];tips=lines[6:]
    return [head+tips[i:i+34] for i in range(0,len(tips),34)]




def make_print_operation(batch,language='de'):
    from gi.repository import Gtk
    pages=pages_for(batch,language)
    operation=Gtk.PrintOperation();operation.set_job_name(f"{batch['game']} #{batch['id']}")
    operation.set_unit(Gtk.Unit.POINTS)
    operation.set_n_pages(len(pages))
    def draw(op,ctx,page):paint_page(ctx.get_cairo_context(),pages[page],ctx.get_width(),ctx.get_height(),page,len(pages))
    operation.connect('draw-page',draw)
    return operation


def print_batch(batch,parent,language='de'):
    from gi.repository import Gtk
    return make_print_operation(batch,language).run(Gtk.PrintOperationAction.PRINT_DIALOG,parent)




def export_batch(batch,path,language='de'):
    """Tippserie als CSV speichern; Jokerwerte behalten führende Nullen."""
    if Path(path).suffix.lower()!='.csv':
        raise ValueError('L014: CSV als Dateiendung verwenden.')
    with atomic_target(path) as temporary,temporary.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['game','batch','created','position','tip','rng_mode','profile'])
        for i,value in enumerate(batch['tips'],1):
            writer.writerow([batch['game'],batch['id'],batch['created'],i,value,batch['rng_mode'],json.dumps(batch['profile'],ensure_ascii=False)])
