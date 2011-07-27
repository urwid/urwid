#!/usr/bin/env python
#
# Urwid LineBox example program
#    Copyright (C) 2011  Yu-Jie Lin
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
Urwid example demonstrating use of the LineBox widget.
"""

import urwid


class LineBoxDemo:

    LBOX_ATTRS = {
        'inset': {
            'tline': 'line dark',
            'lline': 'line dark',
            'tlcorner': 'line dark',
            'blcorner': 'line dark',
            'rline': 'line bright',
            'bline': 'line bright',
            'trcorner': 'line bright',
            'brcorner': 'line bright',
            },
        'outset': {
            'tline': 'line bright',
            'lline': 'line bright',
            'tlcorner': 'line bright',
            'blcorner': 'line bright',
            'rline': 'line dark',
            'bline': 'line dark',
            'trcorner': 'line dark',
            'brcorner': 'line dark',
            },
        'grooved/ridged': {
            'tline': 'line bright/dark',
            'lline': 'line bright/dark',
            'tlcorner': 'line bright/dark',
            'blcorner': 'line bright/dark',
            'rline': 'line dark/bright',
            'bline': 'line dark/bright',
            'trcorner': 'line dark/bright',
            'brcorner': 'line dark/bright',
            },
        'ridged/grooved': {
            'tline': 'line dark/bright',
            'lline': 'line dark/bright',
            'tlcorner': 'line dark/bright',
            'blcorner': 'line dark/bright',
            'rline': 'line bright/dark',
            'bline': 'line bright/dark',
            'trcorner': 'line bright/dark',
            'brcorner': 'line bright/dark',
            },
        'raised/lowered': {
            'tline': 'line bright/dark',
            'lline': 'line bright/dark',
            'tlcorner': 'line bright/dark',
            'blcorner': 'line bright/dark',
            'rline': 'line bright/dark',
            'bline': 'line bright/dark',
            'trcorner': 'line bright/dark',
            'brcorner': 'line bright/dark',
            },
        'lowered/raised': {
            'tline': 'line dark/bright',
            'lline': 'line dark/bright',
            'tlcorner': 'line dark/bright',
            'blcorner': 'line dark/bright',
            'rline': 'line dark/bright',
            'bline': 'line dark/bright',
            'trcorner': 'line dark/bright',
            'brcorner': 'line dark/bright',
            },
        'rainbow': {
            'tline': 'line black',
            'bline': 'line red',
            'lline': 'line green',
            'rline': 'line brown',
            'tlcorner': 'line blue',
            'trcorner': 'line magenta',
            'blcorner': 'line cyan',
            'brcorner': 'line yellow',
            },
        'default': {},
        }

    def __init__(self):

        is_utf8 = urwid.get_encoding_mode() == 'utf8'

        self.custom_style_chars = u'abcdefgh'
        self.lbox_attr =  'default'

        self.style = 'single'
        self.style_chars = None
        lbox = self.create_lbox()
        self.lbox = lbox
        self.style_chars = self.lbox.style_chars

        style_name_width = max(len(name) for name in urwid.LineBox.STYLES.keys())
        style_rows = [('flow', urwid.Text('Styles:'))]
        style_buttons = []
        styles = urwid.LineBox.STYLES.keys()
        styles.sort()
        for style in styles:
            try:
                if not is_utf8:
                  (urwid.LineBox.STYLES[style] or u'').encode('ascii')
            except UnicodeEncodeError:
                text = '    %%-%ds (UTF-8 mode required)' % style_name_width
                row = urwid.Text(text % style)
                row = urwid.AttrMap(row, 'option disable')
                style_rows.append(row)
                continue

            rb = urwid.RadioButton(style_buttons, style, state=style=='single')
            if style != 'custom':
                rb_style_chars = urwid.Text(urwid.LineBox.STYLES[style])
            else:
                rb_style_chars = urwid.Edit('', self.custom_style_chars)
                urwid.connect_signal(rb_style_chars, 'change',
                    self.change_style_chars)
                rb_style_chars = urwid.Padding(
                    urwid.AttrMap(
                        rb_style_chars, 'custom style', 'custom style focus'),
                    width=8)

            urwid.connect_signal(rb, 'change', self.change_style)

            row = urwid.Columns([
                ('fixed', style_name_width + 4, rb),
                rb_style_chars,
                ], dividechars=1)
            
            row = urwid.AttrMap(row, 'option', 'option focus')
            style_rows.append(row)
        self.style_buttons = style_buttons
        style_box = urwid.Pile(style_rows)

        attr_rows = [('flow', urwid.Text('Attributes:'))]
        attr_buttons = []
        attrs = self.LBOX_ATTRS.keys()
        attrs.sort()
        for name in attrs:
            rb = urwid.RadioButton(attr_buttons, name)
            urwid.connect_signal(rb, 'change', self.change_attr)
            row = urwid.AttrMap(rb, 'option', 'option focus')
            attr_rows.append(row)
        self.attr_buttons = attr_buttons
        attr_box = urwid.Pile(attr_rows)

        style_attr_boxes = urwid.Columns([style_box, attr_box], dividechars=1)
        header = urwid.Text('Urwid LineBox example program - F8 exits.')
        header = urwid.AttrMap(header, 'title')

        body = urwid.Pile([
            ('flow', lbox),
            ('flow', urwid.Divider()),
            urwid.Filler(style_attr_boxes, valign='top'),
            ])
        body = urwid.AttrMap(body, 'normal')
        frame = urwid.Frame(body, header=header)
        self.frame = frame
        palette = [
            ('normal', 'black', 'white'),
            ('title', 'white', 'dark red'),
            ('option', 'white', 'dark blue'),
            ('option disable', 'dark gray', 'dark blue'),
            ('option focus', 'white', 'dark green'),
            ('custom style', 'white', 'dark red'),
            ('custom style focus', 'light blue', 'dark red'),
            ('line bright', '', '', '', 'g80', 'white'),
            ('line dark', '', '', '', 'g40', 'white'),
            ('line bright/dark', '', '', '', 'g80', 'g40'),
            ('line dark/bright', '', '', '', 'g40', 'g80'),
            ('line black', 'black', 'white'),
            ('line red', 'dark red', 'white'),
            ('line green', 'dark green', 'white'),
            ('line brown', 'brown', 'white'),
            ('line blue', 'dark blue', 'white'),
            ('line magenta', 'dark magenta', 'white'),
            ('line cyan', 'dark cyan', 'white'),
            ('line yellow', 'yellow', 'white'),
            ]

        loop = urwid.MainLoop(frame, unhandled_input=self.unhandled_input)
        loop.screen.set_terminal_properties(colors=256)
        loop.screen.reset_default_terminal_palette()
        loop.screen.register_palette(palette)
        self.loop = loop

    def create_lbox(self):

        text = urwid.Text('Inside the LineBox')
        return urwid.LineBox(text, 'LineBox Title',
            style=self.style, style_chars=self.style_chars,
            **self.LBOX_ATTRS[self.lbox_attr])

    def change_attr(self, w, state):

        if state:
            self.lbox_attr = w.label
            self.lbox = self.create_lbox()
            self.frame.body.base_widget.widget_list[0] = self.lbox

    def change_style(self, w, state):

        if state:
            if w.label != 'custom':
                self.lbox.set_style(w.label,
                    **self.LBOX_ATTRS[self.lbox_attr])
            else:
                style_chars = self.custom_style_chars[:8]
                style_chars += '?'*(8 - len(style_chars))
                self.lbox.set_style(w.label, style_chars,
                    **self.LBOX_ATTRS[self.lbox_attr])
            self.style = self.lbox.style
            self.style_chars = self.lbox.style_chars

    def change_style_chars(self, w, text):

        self.custom_style_chars = text
        for rbtn in self.style_buttons:
            if rbtn.label == 'custom':
                rbtn.set_state(True, do_callback=False)
                self.change_style(rbtn, True)
                return

    def run(self):

        self.loop.run()
    
    def unhandled_input(self, key):

        if key == 'f8':
            raise urwid.ExitMainLoop


if __name__ == '__main__':
    demo = LineBoxDemo()
    demo.run()
