#!/usr/bin/python3
"""Disposable native GTK app for verifying hidden desktop input."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

window = Gtk.Window(title='CUA Linux probe')
window.set_default_size(800, 600)
window.connect('destroy', Gtk.main_quit)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
window.add(box)
entry = Gtk.Entry()
entry.get_accessible().set_name('Probe text')
box.pack_start(entry, False, False, 12)
button = Gtk.Button(label='Apply text')
button.connect('clicked', lambda _: window.set_title('Applied: ' + entry.get_text()))
box.pack_start(button, False, False, 0)
canvas = Gtk.DrawingArea()
canvas.set_size_request(800, 400)
canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
clicked = False
def draw(widget, cr):
    cr.set_source_rgb(0.1, 0.25, 0.7) if clicked else cr.set_source_rgb(0.7, 0.15, 0.1)
    cr.paint()
    cr.set_source_rgb(1, 1, 1)
    cr.set_font_size(28)
    cr.move_to(100, 100)
    cr.show_text('Canvas clicked' if clicked else 'Click this canvas')
def click(widget, event):
    global clicked
    clicked = True
    window.set_title('Canvas clicked')
    widget.queue_draw()
canvas.connect('draw', draw)
canvas.connect('button-press-event', click)
box.pack_start(canvas, True, True, 0)
window.show_all()
Gtk.main()
