"""Testsonde: sichtbares Fenster der tatsächlich gestarteten DEB-Ausgabe prüfen.

Als sitecustomize.py ausschließlich in der isolierten Prüfinstallation laden.
Der Starter selbst wird unverändert über seine Desktop-Datei ausgeführt.
"""
import os
if os.environ.get('LOTTO_DEB_GUI_PROBE'):
    import json
    from pathlib import Path
    import gi
    gi.require_version('Gtk','4.0')
    gi.require_version('Graphene','1.0')
    gi.require_version('Gsk','4.0')
    from gi.repository import Gtk,GLib,Graphene
    result=Path(os.environ['LOTTO_DEB_GUI_PROBE'])
    def inspect_window():
        windows=[w for w in Gtk.Window.list_toplevels() if w.get_mapped() and '6 aus 45' in (w.get_title() or '')]
        if not windows:return True
        window=windows[0]
        if window.get_width()<100 or window.get_height()<100:return True
        import lotto45
        assert lotto45.VERSION==os.environ['LOTTO_EXPECTED_VERSION']
        paint=Gtk.WidgetPaintable.new(window);snapshot=Gtk.Snapshot.new()
        paint.snapshot(snapshot,float(window.get_width()),float(window.get_height()))
        node=snapshot.to_node()
        if node is None:return True
        bounds=Graphene.Rect();bounds.init(0,0,window.get_width(),window.get_height())
        texture=window.get_native().get_renderer().render_texture(node,bounds)
        texture.save_to_png(str(result.with_suffix('.png')))
        result.write_text(json.dumps({'title':window.get_title(),'mapped':True,'version':lotto45.VERSION,'module':lotto45.__file__,'width':window.get_width(),'height':window.get_height()},indent=2))
        if not os.environ.get('LOTTO_DEB_KEEP_OPEN'):
            GLib.timeout_add(500,lambda:(window.get_application().quit(),False)[1])
        return False
    GLib.timeout_add(250,inspect_window)
