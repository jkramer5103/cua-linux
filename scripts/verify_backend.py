#!/usr/bin/python3
"""Exercise the real MCP backend, preserving screenshots and host-state evidence."""
import base64
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from Xlib import display

ROOT = Path(__file__).resolve().parents[1]
MODE = os.environ.get('CUA_TEST_DISPLAY', 'wayland')
OUT = ROOT / 'artifacts' / MODE
OUT.mkdir(parents=True, exist_ok=True)
host = display.Display()
root = host.screen().root
def host_state():
    focus = host.get_input_focus().focus
    pointer = root.query_pointer()
    return {'focus': getattr(focus, 'id', focus), 'pointer': [pointer.root_x, pointer.root_y]}
before = host_state()
events = []
env = dict(os.environ, OCU_LINUX_DISPLAY=MODE, OCU_MOBILE='0', OCU_EXTRACT='0',
           OCU_XVFB=str(ROOT / '.local/xvfb/usr/bin/Xvfb'))
log = open(OUT / 'backend.stderr.log', 'w')
command = [str(ROOT / 'scripts/mcp.sh')] if os.environ.get('CUA_TEST_BRIDGE') == '1' else [str(ROOT / '.local/bin/opencomputeruse'), 'mcp']
p = subprocess.Popen(command, env=env,
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True)
responses = queue.Queue()
def reader():
    for line in p.stdout:
        responses.put(json.loads(line))
threading.Thread(target=reader, daemon=True).start()
serial = 0
def rpc(method, params):
    global serial
    serial += 1
    p.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': serial, 'method': method, 'params': params}) + '\n')
    p.stdin.flush()
    deadline = time.monotonic() + 40
    while True:
        r = responses.get(timeout=max(0.01, deadline - time.monotonic()))
        if r.get('id') == serial:
            assert 'error' not in r, r
            return r['result']
def tool(name, expect_error=False, **args):
    start = time.monotonic()
    r = rpc('tools/call', {'name': name, 'arguments': args})
    texts = '\n'.join(c['text'] for c in r.get('content', []) if c['type'] == 'text')
    events.append({'tool': name, 'seconds': round(time.monotonic()-start, 3), 'text': texts,
                   'host': host_state()})
    for c in r.get('content', []):
        if c['type'] == 'image':
            (OUT / f'{len(events):02d}-{name}.png').write_bytes(base64.b64decode(c['data']))
    assert bool(r.get('isError')) == expect_error, texts
    print(name, texts[:160], flush=True)
    return texts
session = None
try:
    rpc('initialize', {'protocolVersion':'2025-06-18', 'capabilities':{},
                       'clientInfo':{'name':'cua-linux-verification','version':'0.1'}})
    schemas = rpc('tools/list', {})
    (OUT / 'tools.json').write_text(json.dumps(schemas, indent=2))
    started = json.loads(tool('start_session', app='/usr/bin/python3',
                              args=[str(ROOT / 'scripts/probe_app.py')], display=MODE,
                              display_width=800, display_height=600))
    session = started['session_id']
    for _ in range(40):
        windows = json.loads(tool('list_windows', session_id=session))
        if windows:
            break
        time.sleep(.1)
    assert windows, 'No native window'
    tree = tool('get_ui_tree', session_id=session)
    tool('screenshot', session_id=session)
    field = re.search(r'\[(e\d+)\][^\n]*Probe text', tree)
    assert field, tree
    tool('set_value', session_id=session, element=field[1], value='Background ✓ ä €', ui_tree=True)
    tree = tool('get_ui_tree', session_id=session)
    button = re.search(r'\[(e\d+)\][^\n]*Apply text', tree)
    assert button, tree
    tool('click', session_id=session, element=button[1])
    assert 'Applied: Background ✓ ä €' in tool('list_windows', session_id=session)
    # No element id or tree lookup: a genuinely pixel-driven native action.
    tool('click', session_id=session, x=400, y=300)
    assert 'Canvas clicked' in tool('list_windows', session_id=session)
    tool('click', session_id=session, x=200, y=28, screenshot=False)
    tool('press_key', session_id=session, keys='ctrl+a', screenshot=False)
    tool('type_text', session_id=session, text='Typed ✓ ä €', ui_tree=True)
    assert 'Typed ✓ ä €' in tool('get_ui_tree', session_id=session)
    tool('end_session', session_id=session)
    session = None
    blind = json.loads(tool('start_session', app='/usr/bin/python3',
                            args=[str(ROOT / 'scripts/probe_app.py')], display=MODE,
                            env={'NO_AT_BRIDGE':'1'}, display_width=800, display_height=600))
    session = blind['session_id']
    for _ in range(40):
        if json.loads(tool('list_windows', session_id=session)):
            break
        time.sleep(.1)
    blind_tree = tool('get_ui_tree', session_id=session, expect_error=True)
    assert 'Probe text' not in blind_tree and 'Apply text' not in blind_tree, blind_tree
    tool('screenshot', session_id=session)
    tool('click', session_id=session, x=400, y=300)
    assert 'Canvas clicked' in tool('list_windows', session_id=session)
    tool('click', session_id=session, x=200, y=58 if MODE == 'wayland' else 28, screenshot=False)
    tool('type_text', session_id=session, text='Screenshot only ✓ ä €', screenshot=False)
    tool('click', session_id=session, x=400, y=112 if MODE == 'wayland' else 86)
    assert 'Applied: Screenshot only ✓ ä €' in tool('list_windows', session_id=session)
    if os.environ.get('CUA_TEST_BRIDGE') == '1':
        # The independent native viewer must have decoded the live stream.
        stats = ROOT / 'artifacts/viewer-status.json'
        for _ in range(50):
            if stats.exists():
                info = json.loads(stats.read_text())
                if info.get('frames',0) >= 2:
                    break
            time.sleep(.1)
        assert stats.exists() and info['frames'] >= 2, 'No viewer frames'
    after = host_state()
    report = {'backend': started, 'host_before':before, 'host_after':after,
              'focus_unchanged_at_every_checkpoint':all(e['host']['focus']==before['focus'] for e in events),
              'pointer_unchanged_at_every_checkpoint':all(e['host']['pointer']==before['pointer'] for e in events),
              'screenshot_only_verified':True, 'bridge_tested':os.environ.get('CUA_TEST_BRIDGE')=='1', 'events':events}
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'events'}, indent=2))
finally:
    if session:
        tool('end_session', session_id=session)
    p.stdin.close()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
    log.close()
