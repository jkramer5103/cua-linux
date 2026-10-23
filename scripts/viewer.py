#!/usr/bin/python3
"""Native Cinnamon taskbar window for watching background app sessions."""
import io
import json
import os
from pathlib import Path
import struct
import sys
import threading
import time
import urllib.request
from desktop_env import desktop_environment

for key, value in desktop_environment().items():
    os.environ.setdefault(key, value)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local/python'))
import websocket
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib
from PIL import Image

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp/cua-linux-{os.getuid()}')) / 'cua-linux'

class Viewer(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.jaron.CuaLinux', flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.minimized = '--minimized' in sys.argv
        self.window = None
        self.items = {}
        self.selected = None
        self.picture = None
        self.current = None
        self.generation = 0
        self.frames = 0
        self.last_frame = 0
        self.closed = False
        self.connect('activate', self.activate_view)

    def activate_view(self, app):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='CUA Linux — Background apps')
        self.window.set_wmclass('cua-linux', 'Cua-linux')
        self.window.set_icon_name('preferences-desktop-remote-desktop')
        self.window.set_default_size(1000, 760)
        self.window.set_focus_on_map(not self.minimized)
        if self.minimized:
            self.window.set_accept_focus(False)
        self.window.connect('destroy', lambda *_: setattr(self, 'closed', True))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.window.add(box)
        self.combo = Gtk.ComboBoxText()
        self.combo.connect('changed', self.choose)
        box.pack_start(self.combo, False, False, 0)
        self.status = Gtk.Label(label='Waiting for a background app session…', xalign=0)
        box.pack_start(self.status, False, False, 0)
        self.canvas = Gtk.DrawingArea()
        self.canvas.connect('draw', self.draw)
        box.pack_start(self.canvas, True, True, 0)
        hint = Gtk.Label(label='Live view · minimize to keep working · closing this viewer leaves the agent running', xalign=0)
        box.pack_start(hint, False, False, 0)
        self.window.show_all()
        if self.minimized:
            def minimize():
                self.window.iconify()
                self.window.set_accept_focus(True)
                self.window.set_focus_on_map(True)
                return False
            GLib.timeout_add(100, minimize)
        threading.Thread(target=self.discover, daemon=True).start()
        GLib.timeout_add(200, self.refresh_status)

    def discover(self):
        while not self.closed:
            items = {}
            for path in RUNTIME.glob('*.json'):
                try:
                    registry = json.loads(path.read_text())
                    os.kill(registry['pid'], 0)
                    req = urllib.request.Request(f"http://127.0.0.1:{registry['port']}/sessions",
                                                 headers={'Authorization': 'Bearer '+registry['token']})
                    with urllib.request.urlopen(req, timeout=1) as response:
                        sessions = json.load(response)['sessions']
                    for session in sessions:
                        key = f"{registry['pid']}:{session['session_id']}"
                        items[key] = (registry, session)
                except (OSError, ValueError, KeyError):
                    continue
            GLib.idle_add(self.update_items, items)
            time.sleep(.5)

    def update_items(self, items):
        self.items = items
        if set(items) != set(getattr(self, 'listed', [])):
            previous = self.selected
            self.combo.remove_all()
            self.listed = list(items)
            for key, (_, session) in items.items():
                windows = session.get('windows', [])
                title = windows[0]['title'] if windows else 'Starting…'
                self.combo.append(key, f"{session['session']['app']} — {title}")
            if self.listed:
                preferred = next((k for k, (_, s) in items.items() if s['session_id'] == os.environ.get('CUA_VIEWER_SESSION')), self.listed[0])
                self.combo.set_active_id(previous if previous in items else preferred)
            else:
                self.generation += 1
                self.selected = None
                self.picture = None
        self.canvas.queue_draw()
        return False

    def choose(self, combo):
        key = combo.get_active_id()
        if key == self.selected:
            return
        self.selected = key
        self.generation += 1
        self.picture = None
        if key in self.items:
            threading.Thread(target=self.stream, args=(self.generation, *self.items[key]), daemon=True).start()

    def stream(self, generation, registry, session):
        ws = None
        try:
            ws = websocket.create_connection(
                f"ws://127.0.0.1:{registry['port']}/sessions/{session['session_id']}/view",
                header={'Authorization':'Bearer '+registry['token']}, timeout=2, http_proxy_host=None)
            frame = None
            while not self.closed and generation == self.generation:
                try:
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not msg:
                    break
                if isinstance(msg, str):
                    info = json.loads(msg)
                    if info.get('type') == 'ended':
                        break
                    continue
                if len(msg) < 20:
                    continue
                kind, fmt, flags, wid, x, y, width, height, fullw, fullh = struct.unpack('<BBHIHHHHHH', msg[:20])
                if kind != 1 or not (0 < fullw <= 16384 and 0 < fullh <= 16384):
                    continue
                patch = Image.open(io.BytesIO(msg[20:])).convert('RGB')
                if frame is None or frame.size != (fullw, fullh) or flags & 1:
                    frame = Image.new('RGB', (fullw, fullh))
                frame.paste(patch, (x,y))
                data = GLib.Bytes.new(frame.tobytes())
                pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, fullw, fullh, fullw*3)
                GLib.idle_add(self.show_frame, generation, pixbuf)
        except Exception as error:
            # No token or private connection details in the UI.
            GLib.idle_add(self.stream_error, generation, type(error).__name__)
        finally:
            if ws:
                ws.close()

    def stream_error(self, generation, reason):
        if generation == self.generation:
            self.status.set_text('Live view disconnected: '+reason)
        return False

    def show_frame(self, generation, pixbuf):
        if generation == self.generation:
            self.picture = pixbuf
            self.frames += 1
            self.last_frame = time.time()
            if os.environ.get('CUA_VIEWER_REPORT'):
                target = Path(os.environ['CUA_VIEWER_REPORT'])
                pixbuf.savev(str(target.with_suffix('.png')), 'png', [], [])
                temp = target.with_suffix('.tmp')
                temp.write_text(json.dumps({'frames':self.frames, 'width':pixbuf.get_width(),
                                            'height':pixbuf.get_height(), 'session':self.selected,
                                            'window_visible':self.window.get_visible()}))
                temp.replace(target)
            self.canvas.queue_draw()
        return False

    def refresh_status(self):
        if self.closed:
            return False
        if self.selected in self.items:
            registry, session = self.items[self.selected]
            try:
                registry = json.loads((RUNTIME / f"{registry['pid']}.json").read_text())
            except (OSError, ValueError):
                pass
            self.current = registry
            action = registry.get('action','Waiting').replace('_',' ')
            status = 'Working' if registry.get('busy') else 'Connected'
            if registry.get('failed'):
                status = 'Action failed'
            titles = ', '.join(w['title'] for w in session.get('windows',[]))
            self.status.set_text(f'{status} · {action} · {titles}')
        else:
            self.current = None
            self.status.set_text('Waiting for a background app session…')
        self.canvas.queue_draw()
        report = os.environ.get('CUA_VIEWER_REPORT')
        native = self.window.get_window()
        if report and self.frames and native and not (native.get_state() & Gdk.WindowState.ICONIFIED):
            width, height = native.get_width(), native.get_height()
            screenshot = Gdk.pixbuf_get_from_window(native, 0, 0, width, height)
            if screenshot:
                screenshot.savev(str(Path(report).with_name('viewer-ui.png')), 'png', [], [])
        return True

    def draw(self, widget, cr):
        cr.set_source_rgb(.075,.08,.09)
        cr.paint()
        if self.picture is None:
            return
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        scale = min(width/self.picture.get_width(), height/self.picture.get_height())
        left = (width-self.picture.get_width()*scale)/2
        top = (height-self.picture.get_height()*scale)/2
        cr.save()
        cr.translate(left,top)
        cr.scale(scale,scale)
        Gdk.cairo_set_source_pixbuf(cr,self.picture,0,0)
        cr.paint()
        state = self.current or {}
        if state.get('point') and state.get('point_session') == self.items.get(self.selected, ({},{}))[1].get('session_id'):
            x,y = state['point']
            if x is not None and y is not None:
                cr.set_source_rgba(.2,.85,1,.9)
                cr.set_line_width(2/scale)
                cr.arc(x,y,12,0,6.284)
                cr.stroke()
                cr.arc(x,y,3,0,6.284)
                cr.fill()
        cr.restore()

if __name__ == '__main__':
    Gtk.Window.set_auto_startup_notification(False)
    Viewer().run([sys.argv[0]])
