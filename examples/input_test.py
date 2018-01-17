#!/usr/bin/env python
#
# Urwid keyboard input test app
#    Copyright (C) 2004-2009  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

"""
Keyboard test application
"""

import urwid.curses_display
import urwid.raw_display
import urwid.web_display
import urwid

import sys

if urwid.web_display.is_web_request():
    Screen = urwid.web_display.Screen
else:
    if len(sys.argv)>1 and sys.argv[1][:1] == "r":
        Screen = urwid.raw_display.Screen
    else:
        Screen = urwid.curses_display.Screen

def key_test():
    screen = Screen()
    header = urwid.Text("Values from get_input(). Q exits.")
    header = urwid.AttrWrap(header,'header')
    lw = urwid.SimpleListWalker([])
    listbox = urwid.ListBox(lw)
    listbox = urwid.AttrWrap(listbox, 'listbox')
    top = urwid.Frame(listbox, header)

    def input_filter(keys, raw):
        if 'q' in keys or 'Q' in keys:
            raise urwid.ExitMainLoop

        t = []
        a = []
        for k in keys:
            if type(k) == tuple:
                out = []
                for v in k:
                    if out:
                        out += [', ']
                    out += [('key',repr(v))]
                t += ["("] + out + [")"]
            else:
                t += ["'",('key',k),"' "]

        rawt = urwid.Text(", ".join(["%d"%r for r in raw]))

        if t:
            lw.append(
                urwid.Columns([
                    ('weight',2,urwid.Text(t)),
                    rawt])
                )
            listbox.set_focus(len(lw)-1,'above')
        return keys

    loop = urwid.MainLoop(top, [
        ('header', 'black', 'dark cyan', 'standout'),
        ('key', 'yellow', 'dark blue', 'bold'),
        ('listbox', 'light gray', 'black' ),
        ], screen, input_filter=input_filter)

    try:
        old = screen.tty_signal_keys('undefined','undefined',
            'undefined','undefined','undefined')
        loop.run()
    finally:
        screen.tty_signal_keys(*old)




def main():
    urwid.web_display.set_preferences('Input Test')
    if urwid.web_display.handle_short_request():
        return
    key_test()


if '__main__'==__name__ or urwid.web_display.is_web_request():
    main()
