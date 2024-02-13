#!/usr/bin/env python

from __future__ import annotations

import sys

import urwid

BLACK_FGS = (
    "light gray",
    "dark cyan",
    "dark red",
    "dark green",
    "dark magenta",
    "white",
    "light blue",
    "light cyan",
    "light red",
    "light green",
    "yellow",
    "light magenta",
)
GRAY_FGS = (
    "black",
    "dark blue",
    "dark cyan",
    "dark red",
    "dark green",
    "dark magenta",
    "white",
    "light red",
    "yellow",
    "light magenta",
)
BLUE_FGS = (
    "light gray",
    "dark cyan",
    "white",
    "light cyan",
    "light red",
    "light green",
    "yellow",
    "light magenta",
)
CYAN_FGS = (
    "black",
    "light gray",
    "dark blue",
    "white",
    "light cyan",
    "light green",
    "yellow",
)

BG_FGS = [
    ("black", BLACK_FGS),
    ("light gray", GRAY_FGS),
    ("dark blue", BLUE_FGS),
    ("dark cyan", CYAN_FGS),
]

body = urwid.SimpleFocusListWalker([])

for bg, fgs in BG_FGS:
    spec = urwid.AttrSpec(fgs[0], bg)

    body.extend(
        (
            urwid.AttrMap(urwid.Divider(), spec),
            urwid.AttrMap(
                urwid.GridFlow(
                    (urwid.AttrMap(urwid.Text(f"'{fg}' on '{bg}'"), urwid.AttrSpec(fg, bg)) for fg in fgs),
                    35,
                    0,
                    0,
                    urwid.LEFT,
                ),
                spec,
            ),
            urwid.AttrMap(urwid.Divider(), spec),
        )
    )

try:
    urwid.MainLoop(urwid.ListBox(body)).run()
except KeyboardInterrupt:
    sys.exit(0)
