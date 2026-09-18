"""Gemeinsame Eingabefelder und Tabellen mit beim Scrollen festen Spaltenköpfen."""
import re
from gi.repository import Gtk,GLib


def watch_errors(label,context=''):
    """Fehlercodes im Text rot hervorheben und die Farbe nach Korrektur entfernen."""
    def changed(*_):
        if re.search(r'\bL[0-9]{3}\b',context+' '+label.get_text()):label.add_css_class('lotto-error')
        else:label.remove_css_class('lotto-error')
    label.connect('notify::label',changed);changed();return label


def entry(translate,**kwargs):
    """Das rechte Symbol leert nur dieses Feld und löst dessen normales changed aus."""
    expanded=kwargs.get('hexpand',False)
    kwargs['hexpand']=False
    kwargs.setdefault('halign',Gtk.Align.START)
    kwargs.setdefault('width_chars',22 if expanded else 12)
    kwargs.setdefault('max_width_chars',kwargs['width_chars'])
    widget=Gtk.Entry(**kwargs)
    widget.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,'edit-clear-symbolic')
    widget.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY,translate('clear_input'))
    def changed(*_):widget.set_icon_sensitive(Gtk.EntryIconPosition.SECONDARY,bool(widget.get_text()))
    widget.connect('changed',changed)
    widget.connect('icon-press',lambda field,position:field.set_text('') if position==Gtk.EntryIconPosition.SECONDARY else None)
    changed();return widget


class FixedTable(Gtk.Box):
    """Getrennte Kopf-/Datenbereiche, gemeinsame Spaltenbreiten und horizontale Position.

    Vertikal scrollen ausschließlich die Zeilen. Kopf und Daten verwenden
    dieselbe horizontale Adjustment und je Spalte eine Gtk.SizeGroup.
    """
    def __init__(self,headers,rows,alignments=None,sort=None,selected=None,descending=False,compact=False,row_groups=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=6,hexpand=True,vexpand=not compact)
        self.add_css_class('section-panel')
        self.header=Gtk.Grid(column_spacing=18,row_spacing=6)
        self.body=Gtk.Grid(column_spacing=18,row_spacing=6,valign=Gtk.Align.START)
        self.head_scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL,vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll=Gtk.ScrolledWindow(vexpand=not compact,min_content_height=0 if compact else 90)
        if compact:
            self.scroll.set_propagate_natural_height(True);self.scroll.set_max_content_height(360)
        self.head_scroll.set_hadjustment(self.scroll.get_hadjustment())
        self.head_scroll.set_child(self.header);self.scroll.set_child(self.body)
        self.append(self.head_scroll);self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL));self.append(self.scroll)
        self.groups=[Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL) for _ in headers]
        self.alignments=alignments or [0]*len(headers);self.headers=[];self.cells=[]
        for x,text in enumerate(headers):
            label=Gtk.Label(label=text,xalign=self.alignments[x],wrap=True,max_width_chars=20)
            label.add_css_class('heading')
            if sort:
                # Eigenes Symbol neben der Beschriftung: kein Zeilenumbruch des Pfeils.
                box=Gtk.Box(spacing=6);box.append(label)
                arrow=Gtk.Label(label=('↓' if descending else '↑') if selected==x else '↕')
                box.append(arrow);button=Gtk.Button();button.set_child(box)
                button.connect('clicked',lambda _,i=x:sort(i));cell=button
            else:cell=label
            self.header.attach(cell,x,0,1,1);self.groups[x].add_widget(cell);self.headers.append(cell)
        self.separators=[];grid_y=0
        for y,row in enumerate(rows):
            if row_groups is not None and y>0 and row_groups[y]!=row_groups[y-1]:
                # Linien sind keine Datensätze und ändern weder Zellzugriff noch Seitenzählung.
                line=Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL,hexpand=False)
                self.body.attach(line,0,grid_y,len(headers),1);self.separators.append(line);grid_y+=1
            cells=[]
            for x,text in enumerate(row):
                label=Gtk.Label(label=str(text),xalign=self.alignments[x],yalign=0,selectable=True,wrap=True,max_width_chars=28)
                self.body.attach(label,x,grid_y,1,1);self.groups[x].add_widget(label);cells.append(label)
            self.cells.append(cells)
            grid_y+=1

    def get_child_at(self,x,y):
        return self.headers[x] if y==0 else self.cells[y-1][x]

    def spread(self):
        """Drei Gewinnspalten auf die vom Kugelbereich vorgegebene Breite verteilen."""
        for grid in (self.header,self.body):
            grid.set_column_spacing(12);grid.set_column_homogeneous(True);grid.set_hexpand(True)
        for row in [self.headers,*self.cells]:
            for label in row:label.set_hexpand(True);label.set_max_width_chars(1)

    def get_vadjustment(self):return self.scroll.get_vadjustment()


class ResultArea(Gtk.Box):
    """Tabellen besitzen ihren eigenen Scrollbereich; Karten/Diagramme einen äußeren."""
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,hexpand=True,vexpand=True)
        self.current=None;self.container=None
    def set_child(self,child):
        if self.container:self.remove(self.container)
        self.current=child;self.container=None
        if child is None:return
        if isinstance(child,FixedTable):self.container=child
        else:
            self.container=Gtk.ScrolledWindow(vexpand=True,min_content_height=90)
            self.container.set_child(child)
        self.append(self.container)
    def get_child(self):return self.current
    def get_vadjustment(self):return self.container.get_vadjustment() if self.container else Gtk.Adjustment()


def date_control(field,translate):
    """Kompaktes Datumsfeld mit Kalender daneben; Entry-Schnittstelle bleibt erhalten."""
    from .date_display import parse_input_date
    field.set_width_chars(10);field.set_max_width_chars(10)
    box=Gtk.Box(spacing=2,halign=Gtk.Align.START)
    box.append(field)
    from pathlib import Path
    icon=Path(__file__).resolve().parent.parent/'resources/calendar-3d.svg'
    button=Gtk.MenuButton()
    if icon.is_file():
        picture=Gtk.Image.new_from_file(str(icon));picture.set_pixel_size(24);button.set_child(picture)
    else:button.set_label(translate('calendar_choose'))
    button.update_property([Gtk.AccessibleProperty.LABEL],[translate('calendar_choose')])
    button.set_tooltip_text(translate('calendar_choose'))
    popover=Gtk.Popover();calendar=Gtk.Calendar()
    popover.set_child(calendar);button.set_popover(popover);box.append(button)
    field.calendar=calendar;field.calendar_button=button
    syncing=False
    def opened(*_):
        nonlocal syncing
        if not popover.get_visible():return
        syncing=True
        try:
            try:
                value=parse_input_date(field.get_text())
                date=GLib.DateTime.new_from_iso8601(value+'T12:00:00',GLib.TimeZone.new_local()) if value else GLib.DateTime.new_now_local()
            except ValueError:date=GLib.DateTime.new_now_local()
            calendar.select_day(date)
        finally:syncing=False
    def selected(*_):
        if syncing:return
        field.set_text(calendar.get_date().format('%d.%m.%Y'))
        popover.popdown()
    popover.connect('notify::visible',opened)
    calendar.connect('day-selected',selected)
    return box
