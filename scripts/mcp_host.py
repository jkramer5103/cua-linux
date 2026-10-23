#!/usr/bin/python3
"""Stdio bridge with a private live-view endpoint and a native taskbar viewer."""
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from desktop_env import desktop_environment

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_ENV = desktop_environment()
RUNTIME = Path(DESKTOP_ENV.get('XDG_RUNTIME_DIR', f'/tmp/cua-linux-{os.getuid()}')) / 'cua-linux'
RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
NATIVE_TOOLS = {'start_session','end_session','list_sessions','list_windows','screenshot',
                'get_ui_tree','click','move_mouse','drag','scroll','type_text','press_key',
                'set_value','element_action','choose_file','wait','permissions'}
READ_ONLY_TOOLS = {'list_sessions', 'list_windows', 'screenshot', 'get_ui_tree', 'permissions'}

def viewer_running():
    target = os.fsencode(str(ROOT / 'scripts/viewer.py'))
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid == os.getuid() and target in (proc / 'cmdline').read_bytes().split(b'\0'):
                return True
        except OSError:
            continue
    return False

def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = dict(DESKTOP_ENV, OCU_LINUX_DISPLAY='x11', OCU_MOBILE='0', OCU_EXTRACT='0',
               OCU_CONFIG=str(ROOT / 'backend.json'),
               OCU_XVFB=str(ROOT / '.local/xvfb/usr/bin/Xvfb'))
    for key in ('TYPESAFE_API_KEY','CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_API_TOKEN'):
        env.pop(key, None)
    child = subprocess.Popen([str(ROOT / '.local/bin/opencomputeruse'), 'mcp',
                              '--view-listen', f'127.0.0.1:{port}', '--view-token', token],
                             env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    registry = RUNTIME / f'{os.getpid()}.json'
    state = {'pid':os.getpid(), 'port':port, 'token':token, 'action':'Waiting for a task',
             'busy':False, 'updated':time.time()}
    lock = threading.Lock()
    pending = {}
    nodes = {}
    def publish():
        temp = registry.with_suffix('.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f)
        os.replace(temp, registry)
    publish()
    if os.environ.get('CUA_VIEWER_AUTOOPEN', '1') != '0' and not viewer_running():
        # Start without raising a window or borrowing input focus.
        subprocess.Popen(['/usr/bin/python3', str(ROOT / 'scripts/viewer.py'), '--minimized'],
                         env=DESKTOP_ENV,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    def incoming():
        try:
            for line in sys.stdin:
                request = json.loads(line)
                with lock:
                    pending[request.get('id')] = request
                    if request.get('method') == 'tools/call':
                        args = request.get('params', {}).get('arguments', {})
                        name = request['params'].get('name', '')
                        if name not in NATIVE_TOOLS:
                            reply = {'jsonrpc':'2.0','id':request.get('id'), 'result':{
                                'isError':True,'content':[{'type':'text','text':'This integration exposes native desktop tools only.'}]}}
                            print(json.dumps(reply), flush=True)
                            pending.pop(request.get('id'), None)
                            continue
                        state.update(action=name, busy=True, updated=time.time(),
                                     session=args.get('session_id'))
                        if name in ('click','move_mouse','scroll','drag'):
                            point = [args.get('x', args.get('to_x')), args.get('y', args.get('to_y'))]
                            if point[0] is None:
                                point = nodes.get(args.get('session_id'), {}).get(args.get('element'))
                            state['point'] = point
                            state['point_session'] = args.get('session_id')
                        publish()
                child.stdin.write(line)
                child.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass
        finally:
            child.stdin.close()
    threading.Thread(target=incoming, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        for line in child.stdout:
            response = json.loads(line)
            with lock:
                request = pending.pop(response.get('id'), {})
                if request.get('method') == 'tools/list' and 'result' in response:
                    response['result']['tools'] = [t for t in response['result']['tools'] if t['name'] in NATIVE_TOOLS]
                    for tool in response['result']['tools']:
                        readonly = tool['name'] in READ_ONLY_TOOLS
                        tool['annotations'] = {
                            'title': 'Linux computer use: ' + tool['name'].replace('_', ' '),
                            'readOnlyHint': readonly,
                            'destructiveHint': not readonly,
                            'idempotentHint': readonly,
                            'openWorldHint': not readonly,
                        }
                        tool['description'] = 'Native Linux desktop computer use through cua-linux. ' + tool['description']
                if request.get('method') == 'tools/call':
                    args = request.get('params', {}).get('arguments', {})
                    sid = args.get('session_id')
                    text = '\n'.join(c.get('text','') for c in response.get('result',{}).get('content',[]) if c['type']=='text')
                    found = {}
                    for m in re.finditer(r'\[(e\d+)\][^\n]*?@\(([-\d.]+),([-\d.]+) ([\d.]+)x([\d.]+)\)', text):
                        found[m[1]] = [float(m[2])+float(m[4])/2, float(m[3])+float(m[5])/2]
                    if found and sid:
                        nodes[sid] = found
                    state.update(busy=False, failed=bool(response.get('result',{}).get('isError')), updated=time.time())
                    publish()
            print(json.dumps(response), flush=True)
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        registry.unlink(missing_ok=True)

if __name__ == '__main__':
    main()
