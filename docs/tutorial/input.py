from __future__ import annotations

import urwid


def show_or_exit(key: str) -> None:
    if key in {"q", "Q"}:
        raise urwid.ExitMainLoop()
    txt.set_text(repr(key))


txt = urwid.Text("Hello World")
fill = urwid.Filler(txt, "top")
loop = urwid.MainLoop(fill, unhandled_input=show_or_exit)
loop.run()
