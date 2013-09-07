#!/usr/bin/python
#
# Urwid readline-emulated edit widget example app
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

import textwrap
import urwid

class ReadlineEdit(urwid.ReadlineMixin, urwid.Edit):
    """
    To create an Edit with readline emulated behaviour, just inherit from the
    mixin (it has to be set to the left of the parent class).
    """
    pass

class ReadlineEditWithPasteBuffer(urwid.Frame):
    def __init__(self):
        """Create a frame with:
        - A Text widget that shows the current content of the yank buffer.
        - An Edit widget for the user to write free text and use the
          implemented readline shortcuts.
        """
        self.yank_display = urwid.Text('Yank buffer: (empty)\n------------')
        self.edit = ReadlineEdit(textwrap.dedent('''
        Please type some text. Available shortcuts:
        CTRL-w - delete last word
        CTRL-k - delete the line from the cursor
        CTRL-u - delete the line up to the cursor
        CTRL-y - paste the yank (paste) buffer

        Additional shortcuts:
        F1-F10 - Select word 1-10
        F12    - quit

        '''), multiline=True)
        body = urwid.Filler(self.edit, valign='top')
        super(ReadlineEditWithPasteBuffer, self).__init__(body, header=self.yank_display)
    def keypress(self, size, input):
        ret = super(ReadlineEditWithPasteBuffer, self).keypress(size, input)
        self.yank_display.set_text('Yank buffer: %s\n------------' %
                (self.edit.yank_buffer or '(empty)'))
        import logging; logging.basicConfig(filename='/tmp/example.log',level=logging.DEBUG)
        logging.debug('keypress: %s / returned: %s' % (input, ret))
        return ret

def main():

    def keypress(input):
        if input in ('f12', 'ctrl c'):
            raise urwid.ExitMainLoop()

    frame = ReadlineEditWithPasteBuffer()
    loop = urwid.MainLoop(frame, unhandled_input=keypress)
    loop.run()




if __name__ == '__main__':
    main()
