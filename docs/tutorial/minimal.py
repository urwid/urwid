from __future__ import annotations

import urwid

txt = urwid.Text("Hello World")
fill = urwid.Filler(txt, "top")
loop = urwid.MainLoop(fill)
loop.run()
