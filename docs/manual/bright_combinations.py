#!/usr/bin/env python

from __future__ import annotations

import sys

import urwid

RED_FGS = (
    "black",
    "light gray",
    "white",
    "light cyan",
    "light red",
    "light green",
    "yellow",
    "light magenta",
)
GREEN_FGS = (
    "black",
    "light gray",
    "dark blue",
    "white",
    "light cyan",
    "light red",
    "light green",
    "yellow",
)
BROWN_FGS = (
    "black",
    "dark blue",
    "dark gray",
    "white",
    "light blue",
    "light cyan",
    "light red",
    "light green",
    "yellow",
)
MAGENTA_FGS = (
    "black",
    "light gray",
    "dark blue",
    "white",
    "light cyan",
    "light red",
    "light green",
    "yellow",
    "light magenta",
)

BG_FGS = [
    ("dark red", RED_FGS),
    ("dark green", GREEN_FGS),
    ("brown", BROWN_FGS),
    ("dark magenta", MAGENTA_FGS),
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
