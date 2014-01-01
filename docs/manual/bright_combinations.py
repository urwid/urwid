#!/usr/bin/env python

import urwid

RED_FGS = ('black', 'light gray', 'white', 'light cyan', 'light red',
    'light green', 'yellow', 'light magenta')
GREEN_FGS = ('black', 'light gray', 'dark blue', 'white', 'light cyan',
    'light red', 'light green', 'yellow')
BROWN_FGS = ('black', 'dark blue', 'dark gray', 'white',
    'light blue', 'light cyan', 'light red', 'light green', 'yellow')
MAGENTA_FGS = ('black', 'light gray', 'dark blue', 'white', 'light cyan',
    'light red', 'light green', 'yellow', 'light magenta')

BG_FGS =[
    ('dark red', RED_FGS),
    ('dark green', GREEN_FGS),
    ('brown', BROWN_FGS),
    ('dark magenta', MAGENTA_FGS),
    ]

body = urwid.SimpleFocusListWalker([])

for bg, fgs in BG_FGS:
    spec = urwid.AttrSpec(fgs[0], bg)
    def s(w):
        return urwid.AttrMap(w, spec)
    body.append(s(urwid.Divider()))
    body.append(s(
        urwid.GridFlow(
            [urwid.AttrMap(urwid.Text("'{0}' on '{1}'".format(fg, bg)),
                urwid.AttrSpec(fg, bg)) for fg in fgs],
            35, 0, 0, 'left')))
    body.append(s(urwid.Divider()))

urwid.MainLoop(urwid.ListBox(body)).run()
