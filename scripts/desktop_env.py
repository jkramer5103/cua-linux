"""Recover non-secret desktop routing variables omitted by MCP hosts."""
import os
from pathlib import Path

DESKTOP_KEYS = {
    'DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR',
    'XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION',
    'XDG_SESSION_TYPE', 'GNOME_KEYRING_CONTROL',
}

def desktop_environment():
    env = dict(os.environ)
    # Read only the same user's compositor, not arbitrary app environments.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            if (proc / 'comm').read_text().strip() not in {'cinnamon', 'gnome-shell', 'plasmashell', 'xfce4-session'}:
                continue
            values = (proc / 'environ').read_bytes().split(b'\0')
            for pair in values:
                key, sep, value = pair.partition(b'=')
                name = key.decode(errors='replace')
                if sep and name in DESKTOP_KEYS:
                    env.setdefault(name, value.decode(errors='surrogateescape'))
            break
        except (OSError, ValueError):
            continue
    runtime = Path(f'/run/user/{os.getuid()}')
    if runtime.is_dir() and runtime.stat().st_uid == os.getuid():
        env.setdefault('XDG_RUNTIME_DIR', str(runtime))
        if (runtime / 'bus').is_socket():
            env.setdefault('DBUS_SESSION_BUS_ADDRESS', f'unix:path={runtime}/bus')
    return env
