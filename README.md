# CUA Linux

**Real background computer use on your Linux PC.** Let an AI agent launch
and operate real desktop apps while you keep using your computer. App windows
and input run on a private display, leaving your desktop mouse and keyboard
available to you. A native GTK viewer lets you watch the agent work live.

CUA Linux exposes this through MCP for coding agents. Sessions run on your
actual machine, with access to its filesystem and network; the private display
isolates GUI input, not the rest of the system. Browser control is deliberately
excluded.

## How it works

Codex → `scripts/mcp_host.py` → OpenComputerUse 0.11.0 → private Xvfb display.
AT-SPI provides element targets when an app supports it. Otherwise the agent
reads screenshots and uses coordinates. Input stays on the private display;
there is no fallback to your main desktop's mouse or keyboard.

The native GTK viewer starts minimized. Open **CUA Linux — Background apps**
from the taskbar to watch the session. Its dropdown selects among sessions.
It shows live images, current tool status, and the last agent pointer target.
Minimizing or closing the viewer does not end an app session. Reopen it from
the application menu as **CUA Linux**. The viewer is read-only; it does not
pause the agent or take over input. End the session through Codex when done.

The viewer uses a token-protected loopback connection; tokens are kept in
private files under `$XDG_RUNTIME_DIR/cua-linux/`. Each MCP process gets its
own endpoint. No web browser is opened, and no extra model provider is used.

Codex can launch MCP processes with desktop variables stripped. The bridge
recovers only display, D-Bus and desktop-routing variables from the same
user's compositor, with the existing `/run/user/UID/bus` as a fallback.
This preserves access to the user's unlocked keyring while app pixels and
input still use the private display. The native viewer gets the host display
variables separately. Starting another MCP connection does not raise an
already-running viewer.

## Agent interface

`start_session`, `end_session`, `list_sessions`, `list_windows`, `screenshot`,
`get_ui_tree`, `click`, `move_mouse`, `drag`, `scroll`, `type_text`, `press_key`,
`set_value`, `element_action`, `choose_file`, `wait`, `permissions`.

```json
{"app":"/usr/bin/xcalc", "display":"x11"}
```

Keep the returned `session_id`. `screenshot` returns an MCP image. Actions
also return a fresh screenshot unless `screenshot:false`; `ui_tree:true`
adds accessibility text when available. `get_ui_tree` yields indexed nodes
such as `[e4] Button "Apply" @(0,58 800x34) actions=press`.
An unavailable tree is an explicit error; continue with screenshots.
Coordinates are relative to the session window, using its screenshot grid.
Observe before choosing coordinates, and verify the result after acting.
Do not reuse element ids after another tree read. `end_session` closes the
app; ending the MCP process also ends its sessions.

## Scope and limitations

This launches hidden app instances. It does not attach to arbitrary existing
Cinnamon windows. Apps with a single-instance process or profile lock need
their own profile/new-instance setup; do not launch an app against its active
profile and assume it will remain isolated. AT-SPI availability varies by app.
An X display isolates GUI input, not filesystem or network access.

Private headless Wayland is also supported with `display:"wayland"`, even
on an X11 host. X11 is the configured default. No desktop session is changed.
The GTK test app is verified; compatibility with all installed apps is not.
Signal startup has also been verified from a stripped MCP environment:
the existing database decrypted through the desktop keyring and the app
loaded its conversations. No message-send test was performed in that check.

## Local verification

```sh
CUA_TEST_DISPLAY=x11 /usr/bin/python3 scripts/verify_backend.py
CUA_TEST_DISPLAY=wayland /usr/bin/python3 scripts/verify_backend.py
CUA_TEST_DISPLAY=x11 CUA_TEST_BRIDGE=1 \
  CUA_VIEWER_REPORT="$PWD/artifacts/viewer-status.json" \
  /usr/bin/python3 scripts/verify_backend.py
```

These exercise native GTK element targeting, Unicode text, coordinate clicks
on a canvas, and a second app instance with its AT-SPI bridge disabled.
The latter confirms screenshot-only input by checking the changed window
title. Reports record host pointer/focus at each checkpoint, screenshots,
tool schemas and timings. Host focus can change independently while the user
works; a changed sample alone does not identify the cause. Initial Wayland
testing recorded unchanged host focus and pointer at every checkpoint.
Bridge testing also requires the native viewer to decode multiple live frames.

## Dependencies and provenance

Backend: https://github.com/IAmJSD/OpenComputerUse, release v0.11.0,
source commit `2c53a970ad8bb2c4b2809a41526bb59b1b2cdb11`.
Downloaded x86-64 binary SHA-256:
`6d7c39ac0812295efe8db995c0a03bf828e649fd9f52e6c960ca5ef4bb3440fa`
(verified against GitHub's asset digest).

Xvfb is extracted locally from Ubuntu's `xvfb` package; it was not installed
system-wide. System Python supplies GTK 3, PyGObject, Pillow and python-xlib.
`websocket-client==1.9.2` is installed locally in `.local/python`.
The downloaded binary, extracted Xvfb and inspected source are under `.local/`
and `vendor/`; no source build was performed.

Run the MCP bridge with `scripts/mcp.sh`. Open the viewer directly with
`/usr/bin/python3 scripts/viewer.py`.
