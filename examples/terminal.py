#!/usr/bin/env python
#
# Urwid terminal emulation widget example app
#    Copyright (C) 2010  aszlig
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

import urwid

def main():
    urwid.set_encoding('utf8')
    term = urwid.Terminal(None, encoding='utf-8')

    mainframe = urwid.LineBox(
        urwid.Pile([
            ('weight', 70, term),
            ('fixed', 1, urwid.Filler(urwid.Edit('focus test edit: '))),
        ]),
    )

    def set_title(widget, title):
        mainframe.set_title(title)

    def quit(*args, **kwargs):
        raise urwid.ExitMainLoop()

    def handle_key(key):
        if key in ('q', 'Q'):
            quit()

    urwid.connect_signal(term, 'title', set_title)
    urwid.connect_signal(term, 'closed', quit)

    loop = urwid.MainLoop(
        mainframe,
        handle_mouse=False,
        unhandled_input=handle_key)

    term.main_loop = loop
    loop.run()

if __name__ == '__main__':
    main()
