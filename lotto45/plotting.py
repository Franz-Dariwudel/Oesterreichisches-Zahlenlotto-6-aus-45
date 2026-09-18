"""Matplotlib GTK-4-Diagramme, Systemthema und Tooltips.

Matplotlib erst beim Diagrammaufruf laden. Jede Abbildung trägt den vollständigen
Auswertungsumfang; es gibt keine browserbasierte Darstellung.
"""
from gi.repository import Gtk,GLib
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk4agg import FigureCanvasGTK4Agg
import math
from matplotlib import colors
from matplotlib.ticker import MaxNLocator
from .date_display import format_date


def maximum_ticks(low,high,maximum,integer=False):
    """Exakten Höchstwert ergänzen, ohne dicht benachbarte Beschriftungen."""
    gap=(high-low)*.06
    ticks=MaxNLocator(nbins=6,integer=integer).tick_values(low,high)
    return sorted([float(n) for n in ticks if low<=n<=high and abs(n-maximum)>gap]+[maximum])


class Chart(FigureCanvasGTK4Agg):
    def __init__(self,data,translate,formatter,scope=''):
        self.pair_matrix=data['kind']=='heatmap'
        self.figure=Figure(figsize=(9,9) if self.pair_matrix else (9,5),dpi=100,layout='constrained')
        super().__init__(self.figure)
        self.data=data;self.t=translate;self.fmt=formatter;self.scope=scope
        self.set_hexpand(True);self.set_vexpand(True);self.set_size_request(720,760) if self.pair_matrix else self.set_size_request(600,380)
        self.settings=Gtk.Settings.get_default()
        self.handlers=[self.settings.connect('notify::'+key,lambda *_:GLib.idle_add(self.render)) for key in ('gtk-theme-name','gtk-font-name','gtk-application-prefer-dark-theme')]
        self.mpl_connect('motion_notify_event',self.hover)
        self.connect('map',lambda *_:self.render())
        self.render()

    def close(self):
        for handler in self.handlers:self.settings.disconnect(handler)
        self.handlers=[]

    def render(self):
        style=self.get_style_context();found,color=style.lookup_color('theme_fg_color')
        color=color if found else self.get_color();fg=(color.red,color.green,color.blue)
        found,bg=style.lookup_color('theme_bg_color')
        bg=(bg.red,bg.green,bg.blue) if found else (1,1,1)
        found,accent=style.lookup_color('theme_selected_bg_color');accent=(accent.red,accent.green,accent.blue) if found else fg
        font=self.settings.get_property('gtk-font-name').rsplit(' ',1)
        self.figure.clear();ax=self.figure.add_subplot();self.ax=ax
        self.figure.set_facecolor(bg);ax.set_facecolor(bg);ax.tick_params(colors=fg)
        for spine in ax.spines.values():spine.set_color(fg)
        data=self.data
        raw=[n for row in data.get('matrix',[]) for n in row] if data['type']=='heatmap' else data.get('values',[])
        finite=[float(n) for n in raw if n is not None and math.isfinite(float(n))]
        self.maximum=max(finite) if data['count'] and finite else None
        title=self.t('pattern_'+data['kind']) if self.t('pattern_'+data['kind'])!='pattern_'+data['kind'] else self.t('s_chart_'+data['kind'])
        ax.set_title(title,color=fg,fontfamily=font[0]);self.figure.suptitle(self.scope,color=fg,fontsize=9,wrap=True)
        if self.maximum is not None:
            value=int(self.maximum) if self.maximum.is_integer() else self.maximum
            caption=self.t('chart_max_count' if data['kind']=='frequency' else 'chart_maximum').format(value=self.fmt(value,'int' if self.maximum.is_integer() else 'float'))
            ax.set_title(title+' · '+caption,color=fg,fontfamily=font[0])
        if not data['count'] or not finite:ax.text(.5,.5,self.t('s_empty'),ha='center',transform=ax.transAxes,color=fg)
        elif data['type']=='heatmap':
            import numpy as np
            matrix=np.array([[float('nan') if n is None else n for n in row] for row in data['matrix']])
            cmap=colors.LinearSegmentedColormap.from_list('system',[bg,accent])
            low=min(0,min(finite));high=self.maximum if self.maximum>low else low+1
            heat=ax.imshow(matrix,aspect='equal' if self.pair_matrix else 'auto',interpolation='nearest',cmap=cmap,vmin=low,vmax=high)
            bar=self.figure.colorbar(heat,ax=ax,pad=.02)
            bar.set_ticks(maximum_ticks(low,high,self.maximum,all(n.is_integer() for n in finite)))
            bar.ax.tick_params(colors=fg);bar.outline.set_edgecolor(fg)
            for label in bar.ax.get_yticklabels():label.set_fontfamily(font[0])
            ys_max,xs_max=np.where(matrix==self.maximum)
            ax.scatter(xs_max,ys_max,marker='s',s=65,facecolors='none',edgecolors=fg,linewidths=1)
            xl=data.get('xlabels',data.get('labels',[str(n) for n in range(1,len(matrix[0])+1)]))
            yl=data.get('ylabels',data.get('labels',[str(n) for n in range(1,len(matrix)+1)]))
            xs=list(range(len(xl))) if self.pair_matrix else list(range(0,len(xl),max(1,len(xl)//15)))
            ys=list(range(len(yl))) if self.pair_matrix else list(range(0,len(yl),max(1,len(yl)//15)))
            ax.set_xticks(xs,[xl[i] for i in xs]);ax.set_yticks(ys,[yl[i] for i in ys])
            if self.pair_matrix:
                ax.tick_params(axis='both',labelsize=8,pad=2,length=2)
                ax.tick_params(axis='x',labelrotation=90)
                ax.set_xlim(-.5,len(xl)-.5);ax.set_ylim(len(yl)-.5,-.5)
        else:
            values=data['values'];labels=data['labels'];x=list(range(len(values)))
            if data['type']=='line':
                ax.plot(x,values,color=accent)
                if data.get('reference'):ax.plot(x,data['reference'],color=fg,linestyle='--')
            else:ax.bar(x,values,color=accent)
            # Auch negative Werte und Referenzlinien bleiben vollständig sichtbar.
            low,high=ax.get_ylim()
            ax.set_yticks(maximum_ticks(low,high,self.maximum,all(n.is_integer() for n in finite)))
            ax.set_ylim(low,high)
            ax.axhline(self.maximum,color=fg,linestyle=':',linewidth=.8,alpha=.6)
            step=max(1,len(x)//12);indices=x[::step]
            ax.set_xticks(indices,[format_date(labels[i]) if data['type']=='line' else str(labels[i]) for i in indices],rotation=30 if len(indices)>8 else 0)
        ax.set_xlabel(self.t(data['x_title']),color=fg);ax.set_ylabel(self.t(data['y_title']),color=fg)
        for text in ax.get_xticklabels()+ax.get_yticklabels():text.set_fontfamily(font[0])
        self.draw_idle()

    def hover(self,event):
        if event.inaxes is not self.ax or event.xdata is None:self.set_tooltip_text(None);return
        d=self.data
        try:
            x=round(event.xdata)
            if x<0:raise IndexError
            if d['type']=='heatmap':
                y=round(event.ydata)
                if y<0:raise IndexError
                text=f'{y+1} / {x+1}: {d["matrix"][y][x]}'
            else:text=f'{d["labels"][x]}: {d["values"][x]}'
            self.set_tooltip_text(text)
        except (IndexError,TypeError):self.set_tooltip_text(None)


