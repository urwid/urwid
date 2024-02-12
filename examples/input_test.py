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
# Urwid web site: https://urwid.org/

"""
Keyboard test application
"""

from __future__ import annotations

import argparse
import logging

import urwid

if urwid.display.web.is_web_request():
    Screen = urwid.display.web.Screen
    loop_cls = urwid.SelectEventLoop
else:
    event_loops: dict[str, type[urwid.EventLoop] | None] = {
        "none": None,
        "select": urwid.SelectEventLoop,
        "asyncio": urwid.AsyncioEventLoop,
    }
    if hasattr(urwid, "TornadoEventLoop"):
        event_loops["tornado"] = urwid.TornadoEventLoop
    if hasattr(urwid, "GLibEventLoop"):
        event_loops["glib"] = urwid.GLibEventLoop
    if hasattr(urwid, "TwistedEventLoop"):
        event_loops["twisted"] = urwid.TwistedEventLoop
    if hasattr(urwid, "TrioEventLoop"):
        event_loops["trio"] = urwid.TrioEventLoop
    if hasattr(urwid, "ZMQEventLoop"):
        event_loops["zmq"] = urwid.ZMQEventLoop

    parser = argparse.ArgumentParser(description="Input test")
    parser.add_argument(
        "argc",
        help="Positional arguments ('r' for raw display)",
        metavar="<arguments>",
        nargs="*",
        default=(),
    )
    group = parser.add_argument_group("Advanced Options")
    group.add_argument(
        "--event-loop",
        choices=event_loops,
        default="none",
        help="Event loop to use ('none' = use the default)",
    )
    group.add_argument("--debug-log", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if not hasattr(urwid.display, "curses") or "r" in args.argc:
        Screen = urwid.display.raw.Screen
    else:
        Screen = urwid.display.curses.Screen

    loop_cls = event_loops[args.event_loop]

    if args.debug_log:
        logging.basicConfig(
            level=logging.DEBUG,
            filename="debug.log",
            format=(
                "%(levelname)1.1s %(asctime)s | %(threadName)s | %(name)s \n"
                "\t%(message)s\n"
                "-------------------------------------------------------------------------------"
            ),
            datefmt="%d-%b-%Y %H:%M:%S",
            force=True,
        )
        logging.captureWarnings(True)


def key_test():
    screen = Screen()
    header = urwid.AttrMap(
        urwid.Text("Values from get_input(). Q exits."),
        "header",
    )
    lw = urwid.SimpleListWalker([])
    listbox = urwid.AttrMap(
        urwid.ListBox(lw),
        "listbox",
    )
    top = urwid.Frame(listbox, header)

    def input_filter(keys, raw):
        if "q" in keys or "Q" in keys:
            raise urwid.ExitMainLoop

        t = []
        for k in keys:
            if isinstance(k, tuple):
                out = []
                for v in k:
                    if out:
                        out += [", "]
                    out += [("key", repr(v))]
                t += ["(", *out, ")"]
            else:
                t += ["'", ("key", k), "' "]

        rawt = urwid.Text(", ".join(f"{r:d}" for r in raw))

        if t:
            lw.append(urwid.Columns([(urwid.WEIGHT, 2, urwid.Text(t)), rawt]))
            listbox.original_widget.set_focus(len(lw) - 1, "above")
        return keys

    loop = urwid.MainLoop(
        top,
        [
            ("header", "black", "dark cyan", "standout"),
            ("key", "yellow", "dark blue", "bold"),
            ("listbox", "light gray", "black"),
        ],
        screen,
        input_filter=input_filter,
        event_loop=loop_cls() if loop_cls is not None else None,
    )

    old = ()

    try:
        old = screen.tty_signal_keys("undefined", "undefined", "undefined", "undefined", "undefined")
        loop.run()
    finally:
        if old:
            screen.tty_signal_keys(*old)


def main():
    urwid.display.web.set_preferences("Input Test")
    if urwid.display.web.handle_short_request():
        return
    key_test()


if __name__ == "__main__" or urwid.display.web.is_web_request():
    main()
