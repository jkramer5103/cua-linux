---
name: cua-linux
description: Use native Linux desktop apps in background sessions with accessibility or screenshots and a live Cinnamon taskbar viewer. Use for computer use, GUI interaction, or tasks in desktop apps such as Signal, editors, or calculators. Browser websites use the existing browser tools.
---

# Native Linux computer use

The `cua-linux` MCP server is installed on this machine. It is separate from
the built-in `cua_repl` browser interface. A built-in inventory containing only
Chrome tabs does not indicate whether this native-app server is available.

Find tools belonging to the `cua-linux` server. With deferred tools, search
the tool inventory by the server name, allowing hyphens or underscores:
`/cua[-_]linux/i`. Its native entry point is `start_session`; capabilities
are reported by `permissions`. Do not conclude that native computer use is
unavailable solely from the built-in browser inventory or old desktop notes.
If these MCP tools really are absent, report that the current client has not
loaded the configured server; a full Codex process restart may be needed.

Use `permissions` and `list_sessions` to orient. Launch the requested app
with `start_session`, keeping the returned session id. Linux uses a private
X11 display by default and does not touch the user's main pointer or focus.
The viewer opens minimized in the Cinnamon taskbar as **CUA Linux**; opening,
minimizing or closing that viewer does not interrupt the app session.

Read `get_ui_tree` for element ids and available actions. `screenshot` returns
an image. When the app has no tree, inspect the screenshot and use coordinates
relative to that image. An unavailable accessibility tree is not a computer-use
blocker. Actions return screenshots by default; verify the visible result.
Refresh element ids after new tree reads. `set_value`, `element_action`,
`click`, `type_text`, `press_key`, `scroll` and `drag` operate on the session.
Electron apps can need `--force-renderer-accessibility` in launch arguments.

These are newly launched app instances, not attachments to existing visible
windows. Check single-instance/profile behavior before launching an app that
is already running; never fall back to focusing or driving the live desktop.
When an app is not running, inspect its supported launch options and saved
configuration rather than assuming it must be linked again. Do not copy or
modify account databases to bypass a profile lock. If login is required, let
the user use the viewer or explain the exact authentication limitation.

Respect the requested task and its authorization. This skill does not grant
permission to send messages or change external state. End sessions when their
work is done; ending a session closes apps it launched.

Implementation and limitations:
`/home/jaron/Desktop/Programming_Stuff/cua-linux/README.md`.
