from __future__ import annotations

import urwid


def exit_on_q(key):
    if key in {"q", "Q"}:
        raise urwid.ExitMainLoop()


palette = [
    ("banner", "", "", "", "#ffa", "#60d"),
    ("streak", "", "", "", "g50", "#60a"),
    ("inside", "", "", "", "g38", "#808"),
    ("outside", "", "", "", "g27", "#a06"),
    ("bg", "", "", "", "g7", "#d06"),
]

placeholder = urwid.SolidFill()
loop = urwid.MainLoop(placeholder, palette, unhandled_input=exit_on_q)
loop.screen.set_terminal_properties(colors=256)
loop.widget = urwid.AttrMap(placeholder, "bg")
loop.widget.original_widget = urwid.Filler(urwid.Pile([]))

div = urwid.Divider()
outside = urwid.AttrMap(div, "outside")
inside = urwid.AttrMap(div, "inside")
txt = urwid.Text(("banner", " Hello World "), align="center")
streak = urwid.AttrMap(txt, "streak")
pile = loop.widget.base_widget  # .base_widget skips the decorations
for item in (outside, inside, streak, inside, outside):
    pile.contents.append((item, pile.options()))

loop.run()
