"""Interaktive GTK-/Cairo-Diagramme mit Schrift und Farben aus dem Systemthema.

Alle Punkte/Matrixzellen bleiben enthalten. Tooltip zeigt den genauen Wert.
Bei kurzen Zeitfenstern werden keine fehlenden Ziehungen ergänzt.
"""
import math
import gi
gi.require_version('Gtk','4.0')
gi.require_version('PangoCairo','1.0')
gi.require_foreign('cairo')
from gi.repository import Gtk,PangoCairo


class Chart(Gtk.DrawingArea):
    def __init__(self,data,translate,formatter):
        super().__init__(hexpand=True,vexpand=True)
        self.data=data;self.t=translate;self.fmt=formatter;self.bounds=None;self.hover=None
        self.set_content_width(640);self.set_content_height(420)
        self.set_draw_func(self.draw)
        motion=Gtk.EventControllerMotion();motion.connect('motion',self.motion);motion.connect('leave',self.leave);self.add_controller(motion)
        self.settings=Gtk.Settings.get_default()
        self.handlers=[self.settings.connect('notify::'+name,lambda *_:self.queue_draw()) for name in ('gtk-theme-name','gtk-font-name','gtk-application-prefer-dark-theme')]

    def close(self):
        for handler in self.handlers:self.settings.disconnect(handler)
        self.handlers=[]

    def text(self,cr,text,x,y,align=0):
        layout=self.create_pango_layout(str(text));width,height=layout.get_pixel_size()
        cr.move_to(x-width*align,y);PangoCairo.show_layout(cr,layout)
        return width,height

    def colors(self):
        fg=self.get_color();found,accent=self.get_style_context().lookup_color('accent_color')
        return fg,accent if found else fg

    @staticmethod
    def color(cr,color,alpha=1):cr.set_source_rgba(color.red,color.green,color.blue,color.alpha*alpha)

    def draw(self,area,cr,width,height):
        fg,accent=self.colors();self.color(cr,fg)
        if not self.data['count']:
            self.text(cr,self.t('s_empty'),24,24);return
        if self.data['type']=='heatmap':self.draw_heatmap(cr,width,height,fg,accent);return
        left,top,right,bottom=70,30,width-25,height-95
        values=self.data['values'];reference=self.data.get('reference',[])
        if not values:return
        lo=min([0,*values,*reference]);hi=max([0,*values,*reference])
        if lo==hi:hi=lo+1
        raw_step=(hi-lo)/5;unit=10**math.floor(math.log10(raw_step))
        step=next(n*unit for n in (1,2,5,10) if n*unit>=raw_step)
        if self.data['type']=='bar':step=max(1,math.ceil(step))
        lo=math.floor(lo/step)*step;hi=math.ceil(hi/step)*step
        plot_width=right-left;plot_height=bottom-top
        px=lambda i:left+(i+.5)*plot_width/len(values)
        py=lambda value:bottom-(value-lo)/(hi-lo)*plot_height
        self.bounds=(left,top,right,bottom)
        for i in range(round((hi-lo)/step)+1):
            value=lo+i*step;y=py(value)
            self.color(cr,fg,.15);cr.move_to(left,y);cr.line_to(right,y);cr.stroke()
            self.color(cr,fg);self.text(cr,self.fmt(int(value),'int') if self.data['type']=='bar' else self.fmt(value,'float'),left-9,y-8,1)
        self.color(cr,fg);cr.move_to(left,top);cr.line_to(left,bottom);cr.line_to(right,bottom);cr.stroke()
        self.text(cr,self.t(self.data['y_title']),left,3)
        if self.data['type']=='bar':
            bar_width=plot_width/len(values)*.74
            for i,value in enumerate(values):
                if value==0:continue
                self.color(cr,accent,1 if self.hover==i else .78)
                cr.rectangle(px(i)-bar_width/2,min(py(value),py(0)),bar_width,max(1,abs(py(0)-py(value))));cr.fill()
            tick=max(1,math.ceil(len(values)/15))
        else:
            self.color(cr,accent);cr.set_line_width(1.7)
            for i,value in enumerate(values):
                if i:cr.line_to(px(i),py(value))
                else:cr.move_to(px(i),py(value))
            cr.stroke()
            if len(values)==1:cr.arc(px(0),py(values[0]),3,0,2*math.pi);cr.fill()
            self.color(cr,fg,.6);cr.set_dash([5,4]);cr.set_line_width(1)
            # Auch bei nur einer Ziehung bleibt der Erwartungswert als Linie sichtbar.
            if reference:
                cr.move_to(left,py(reference[0]))
                for i,value in enumerate(reference):cr.line_to(px(i),py(value))
                cr.line_to(right,py(reference[-1]))
            cr.stroke();cr.set_dash([])
            tick=max(1,math.ceil(len(values)/4))
        self.color(cr,fg)
        ticks=set(range(0,len(values),tick))|{len(values)-1}
        for i in sorted(ticks):
            label=self.data['labels'][i]
            if self.data['type']=='line':label=self.fmt(label,'date')
            align=0 if i==0 else 1 if i==len(values)-1 else .5
            self.text(cr,label,px(i),bottom+9,align if self.data['type']=='line' else .5)
        self.text(cr,self.t(self.data['x_title']),(left+right)/2,height-45,.5)
        if reference:
            self.text(cr,self.t('s_chart_reference'),left,height-23)
        if isinstance(self.hover,int) and 0<=self.hover<len(values):
            self.color(cr,fg,.45);cr.move_to(px(self.hover),top);cr.line_to(px(self.hover),bottom);cr.stroke()

    def draw_heatmap(self,cr,width,height,fg,accent):
        left,top=55,30;side=min(width-110,height-110);cell=side/45
        self.bounds=(left,top,left+side,top+side)
        matrix=self.data['matrix'];maximum=max((v for row in matrix for v in row if v is not None),default=1) or 1
        for y,row in enumerate(matrix):
            for x,value in enumerate(row):
                if value is None:continue
                self.color(cr,accent,.05+.95*value/maximum)
                cr.rectangle(left+x*cell,top+y*cell,cell-.3,cell-.3);cr.fill()
        self.color(cr,fg)
        for n in (1,5,10,15,20,25,30,35,40,45):
            self.text(cr,f'{n:02d}',left+(n-.5)*cell,top+side+6,.5)
            self.text(cr,f'{n:02d}',left-9,top+(n-.5)*cell-8,1)
        self.text(cr,self.t('s_number'),left+side/2,top+side+32,.5)
        self.text(cr,self.t('s_heat_scale').format(maximum=self.fmt(maximum,'int')),left,top+side+58)
        if isinstance(self.hover,tuple):
            x,y=self.hover;self.color(cr,fg);cr.set_line_width(2)
            cr.rectangle(left+x*cell,top+y*cell,cell,cell);cr.stroke()

    def motion(self,controller,x,y):
        if not self.bounds:return
        left,top,right,bottom=self.bounds
        if not left<=x<right or not top<=y<bottom:self.leave(controller);return
        if self.data['type']=='heatmap':
            col=min(44,int((x-left)/(right-left)*45));row=min(44,int((y-top)/(bottom-top)*45));hover=(col,row)
            value=self.data['matrix'][row][col]
            text=self.t('s_diagonal') if value is None else f'{row+1:02d} + {col+1:02d}: '+self.t('s_pair_tooltip').format(count=self.fmt(value,'int'))
        else:
            values=self.data['values'];hover=min(len(values)-1,int((x-left)/(right-left)*len(values)))
            value=self.fmt(values[hover],'percent' if self.data['kind']=='timeline' else 'float' if self.data['type']=='line' else 'int')
            if self.data.get('lower_bounds') and self.data['lower_bounds'][hover]:value='≥'+value
            label=self.data['labels'][hover]
            if self.data['type']=='line':label=self.fmt(label,'date')+f' (#{hover+1})'
            text=label+': '+value
        if hover!=self.hover:self.hover=hover;self.set_tooltip_text(text);self.queue_draw()

    def leave(self,controller):
        if self.hover is not None:self.hover=None;self.set_tooltip_text(None);self.queue_draw()
