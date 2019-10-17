#!/usr/bin/env python
#
# Urwid tour.  It slices, it dices..
#    Copyright (C) 2004-2011  Ian Ward
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
Urwid tour.  Shows many of the standard widget types and features.
"""

import urwid
import urwid.raw_display
import urwid.web_display

def main():
    text_header = (u"Welcome to the urwid tour!  "
        u"UP / DOWN / PAGE UP / PAGE DOWN scroll.  F8 exits.")
    text_intro = [('important', u"Text"),
        u" widgets are the most common in "
        u"any urwid program.  This Text widget was created "
        u"without setting the wrap or align mode, so it "
        u"defaults to left alignment with wrapping on space "
        u"characters.  ",
        ('important', u"Change the window width"),
        u" to see how the widgets on this page react.  "
        u"This Text widget is wrapped with a ",
        ('important', u"Padding"),
        u" widget to keep it indented on the left and right."]
    text_right = (u"This Text widget is right aligned.  Wrapped "
        u"words stay to the right as well. ")
    text_center = u"This one is center aligned."
    text_clip = (u"Text widgets may be clipped instead of wrapped.\n"
        u"Extra text is discarded instead of wrapped to the next line. "
        u"65-> 70-> 75-> 80-> 85-> 90-> 95-> 100>\n"
        u"Newlines embedded in the string are still respected.")
    text_right_clip = (u"This is a right aligned and clipped Text widget.\n"
        u"<100 <-95 <-90 <-85 <-80 <-75 <-70 <-65             "
        u"Text will be cut off at the left of this widget.")
    text_center_clip = (u"Center aligned and clipped widgets will have "
        u"text cut off both sides.")
    text_ellipsis = (u"Text can be clippped using the ellipsis character (…)\n"
        u"Extra text is discarded and a … mark is shown."
         u"50-> 55-> 60-> 65-> 70-> 75-> 80-> 85-> 90-> 95-> 100>\n"
    )
    text_any = (u"The 'any' wrap mode will wrap on any character.  This "
        u"mode will not collapse space characters at the end of the "
        u"line but it still honors embedded newline characters.\n"
        u"Like this one.")
    text_padding = (u"Padding widgets have many options.  This "
        u"is a standard Text widget wrapped with a Padding widget "
        u"with the alignment set to relative 20% and with its width "
        u"fixed at 40.")
    text_divider =  [u"The ", ('important', u"Divider"),
        u" widget repeats the same character across the whole line.  "
        u"It can also add blank lines above and below."]
    text_edit = [u"The ", ('important', u"Edit"),
        u" widget is a simple text editing widget.  It supports cursor "
        u"movement and tries to maintain the current column when focus "
        u"moves to another edit widget.  It wraps and aligns the same "
        u"way as Text widgets." ]
    text_edit_cap1 = ('editcp', u"This is a caption.  Edit here: ")
    text_edit_text1 = u"editable stuff"
    text_edit_cap2 = ('editcp', u"This one supports newlines: ")
    text_edit_text2 = (u"line one starts them all\n"
        u"== line 2 == with some more text to edit.. words.. whee..\n"
        u"LINE III, the line to end lines one and two, unless you "
        u"change something.")
    text_edit_cap3 = ('editcp', u"This one is clipped, try "
        u"editing past the edge: ")
    text_edit_text3 = u"add some text here -> -> -> ...."
    text_edit_alignments = u"Different Alignments:"
    text_edit_left = u"left aligned (default)"
    text_edit_center = u"center aligned"
    text_edit_right = u"right aligned"
    text_intedit = ('editcp', [('important', u"IntEdit"),
        u" allows only numbers: "])
    text_edit_padding = ('editcp', u"Edit widget within a Padding widget ")
    text_columns1 = [('important', u"Columns"),
        u" are used to share horizontal screen space.  "
        u"This one splits the space into two parts with "
        u"three characters between each column.  The "
        u"contents of each column is a single widget."]
    text_columns2 = [u"When you need to put more than one "
        u"widget into a column you can use a ",('important',
        u"Pile"), u" to combine two or more widgets."]
    text_col_columns = u"Columns may be placed inside other columns."
    text_col_21 = u"Col 2.1"
    text_col_22 = u"Col 2.2"
    text_col_23 = u"Col 2.3"
    text_column_widths = (u"Columns may also have uneven relative "
        u"weights or fixed widths.  Use a minimum width so that "
        u"columns don't become too small.")
    text_weight = u"Weight %d"
    text_fixed_9 = u"<Fixed 9>" # should be 9 columns wide
    text_fixed_14 = u"<--Fixed 14-->" # should be 14 columns wide
    text_edit_col_cap1 = ('editcp', u"Edit widget within Columns")
    text_edit_col_text1 = u"here's\nsome\ninfo"
    text_edit_col_cap2 = ('editcp', u"and within Pile ")
    text_edit_col_text2 = u"more"
    text_edit_col_cap3 = ('editcp', u"another ")
    text_edit_col_text3 = u"still more"
    text_gridflow = [u"A ",('important', u"GridFlow"), u" widget "
        u"may be used to display a list of flow widgets with equal "
        u"widths.  Widgets that don't fit on the first line will "
        u"flow to the next.  This is useful for small widgets that "
        u"you want to keep together such as ", ('important', u"Button"),
        u", ",('important', u"CheckBox"), u" and ",
        ('important', u"RadioButton"), u" widgets." ]
    text_button_list = [u"Yes", u"No", u"Perhaps", u"Certainly", u"Partially",
        u"Tuesdays Only", u"Help"]
    text_cb_list = [u"Wax", u"Wash", u"Buff", u"Clear Coat", u"Dry",
        u"Racing Stripe"]
    text_rb_list = [u"Morning", u"Afternoon", u"Evening", u"Weekend"]
    text_listbox = [u"All these widgets have been displayed "
        u"with the help of a ", ('important', u"ListBox"), u" widget.  "
        u"ListBox widgets handle scrolling and changing focus.  A ",
        ('important', u"Frame"), u" widget is used to keep the "
        u"instructions at the top of the screen."]


    def button_press(button):
        frame.footer = urwid.AttrWrap(urwid.Text(
            [u"Pressed: ", button.get_label()]), 'header')

    radio_button_group = []

    blank = urwid.Divider()
    listbox_content = [
        blank,
        urwid.Padding(urwid.Text(text_intro), left=2, right=2, min_width=20),
        blank,
        urwid.Text(text_right, align='right'),
        blank,
        urwid.Text(text_center, align='center'),
        blank,
        urwid.Text(text_clip, wrap='clip'),
        blank,
        urwid.Text(text_right_clip, align='right', wrap='clip'),
        blank,
        urwid.Text(text_center_clip, align='center', wrap='clip'),
        blank,
        urwid.Text(text_ellipsis, wrap='ellipsis'),
        blank,
        urwid.Text(text_any, wrap='any'),
        blank,
        urwid.Padding(urwid.Text(text_padding), ('relative', 20), 40),
        blank,
        urwid.AttrWrap(urwid.Divider("=", 1), 'bright'),
        urwid.Padding(urwid.Text(text_divider), left=2, right=2, min_width=20),
        urwid.AttrWrap(urwid.Divider("-", 0, 1), 'bright'),
        blank,
        urwid.Padding(urwid.Text(text_edit), left=2, right=2, min_width=20),
        blank,
        urwid.AttrWrap(urwid.Edit(text_edit_cap1, text_edit_text1),
            'editbx', 'editfc'),
        blank,
        urwid.AttrWrap(urwid.Edit(text_edit_cap2, text_edit_text2,
            multiline=True ), 'editbx', 'editfc'),
        blank,
        urwid.AttrWrap(urwid.Edit(text_edit_cap3, text_edit_text3,
            wrap='clip' ), 'editbx', 'editfc'),
        blank,
        urwid.Text(text_edit_alignments),
        urwid.AttrWrap(urwid.Edit("", text_edit_left, align='left'),
            'editbx', 'editfc' ),
        urwid.AttrWrap(urwid.Edit("", text_edit_center,
            align='center'), 'editbx', 'editfc' ),
        urwid.AttrWrap(urwid.Edit("", text_edit_right, align='right'),
            'editbx', 'editfc' ),
        blank,
        urwid.AttrWrap(urwid.IntEdit(text_intedit, 123),
            'editbx', 'editfc' ),
        blank,
        urwid.Padding(urwid.AttrWrap(urwid.Edit(text_edit_padding, ""),
            'editbx','editfc' ), left=10, width=50),
        blank,
        blank,
        urwid.AttrWrap(urwid.Columns([
            urwid.Divider("."),
            urwid.Divider(","),
            urwid.Divider("."),
            ]), 'bright'),
        blank,
        urwid.Columns([
            urwid.Padding(urwid.Text(text_columns1), left=2, right=0,
                min_width=20),
            urwid.Pile([
                urwid.Divider("~"),
                urwid.Text(text_columns2),
                urwid.Divider("_")])
            ], 3),
        blank,
        blank,
        urwid.Columns([
            urwid.Text(text_col_columns),
            urwid.Columns([
                urwid.Text(text_col_21),
                urwid.Text(text_col_22),
                urwid.Text(text_col_23),
                ], 1),
            ], 2),
        blank,
        urwid.Padding(urwid.Text(text_column_widths), left=2, right=2,
            min_width=20),
        blank,
        urwid.Columns( [
            urwid.AttrWrap(urwid.Text(text_weight % 1),'reverse'),
            ('weight', 2, urwid.Text(text_weight % 2)),
            ('weight', 3, urwid.AttrWrap(urwid.Text(
                text_weight % 3), 'reverse')),
            ('weight', 4, urwid.Text(text_weight % 4)),
            ('weight', 5, urwid.AttrWrap(urwid.Text(
                text_weight % 5), 'reverse')),
            ('weight', 6, urwid.Text(text_weight % 6)),
            ], 0, min_width=8),
        blank,
        urwid.Columns([
            ('weight', 2, urwid.AttrWrap(urwid.Text(
                text_weight % 2), 'reverse')),
            ('fixed', 9, urwid.Text(text_fixed_9)),
            ('weight', 3, urwid.AttrWrap(urwid.Text(
                text_weight % 2), 'reverse')),
            ('fixed', 14, urwid.Text(text_fixed_14)),
            ], 0, min_width=8),
        blank,
        urwid.Columns([
            urwid.AttrWrap(urwid.Edit(text_edit_col_cap1,
                text_edit_col_text1, multiline=True),
                'editbx','editfc'),
            urwid.Pile([
                urwid.AttrWrap(urwid.Edit(
                    text_edit_col_cap2,
                    text_edit_col_text2),
                    'editbx','editfc'),
                blank,
                urwid.AttrWrap(urwid.Edit(
                    text_edit_col_cap3,
                    text_edit_col_text3),
                    'editbx','editfc'),
                ]),
            ], 1),
        blank,
        urwid.AttrWrap(urwid.Columns([
            urwid.Divider("'"),
            urwid.Divider('"'),
            urwid.Divider("~"),
            urwid.Divider('"'),
            urwid.Divider("'"),
            ]), 'bright'),
        blank,
        blank,
        urwid.Padding(urwid.Text(text_gridflow), left=2, right=2,
            min_width=20),
        blank,
        urwid.Padding(urwid.GridFlow(
            [urwid.AttrWrap(urwid.Button(txt, button_press),
                'buttn','buttnf') for txt in text_button_list],
            13, 3, 1, 'left'),
            left=4, right=3, min_width=13),
        blank,
        urwid.Padding(urwid.GridFlow(
            [urwid.AttrWrap(urwid.CheckBox(txt),'buttn','buttnf')
                for txt in text_cb_list],
            10, 3, 1, 'left') ,
            left=4, right=3, min_width=10),
        blank,
        urwid.Padding(urwid.GridFlow(
            [urwid.AttrWrap(urwid.RadioButton(radio_button_group,
                txt), 'buttn','buttnf')
                for txt in text_rb_list],
            13, 3, 1, 'left') ,
            left=4, right=3, min_width=13),
        blank,
        blank,
        urwid.Padding(urwid.Text(text_listbox), left=2, right=2,
            min_width=20),
        blank,
        blank,
        ]

    header = urwid.AttrWrap(urwid.Text(text_header), 'header')
    listbox = urwid.ListBox(urwid.SimpleListWalker(listbox_content))
    frame = urwid.Frame(urwid.AttrWrap(listbox, 'body'), header=header)

    palette = [
        ('body','black','light gray', 'standout'),
        ('reverse','light gray','black'),
        ('header','white','dark red', 'bold'),
        ('important','dark blue','light gray',('standout','underline')),
        ('editfc','white', 'dark blue', 'bold'),
        ('editbx','light gray', 'dark blue'),
        ('editcp','black','light gray', 'standout'),
        ('bright','dark gray','light gray', ('bold','standout')),
        ('buttn','black','dark cyan'),
        ('buttnf','white','dark blue','bold'),
        ]


    # use appropriate Screen class
    if urwid.web_display.is_web_request():
        screen = urwid.web_display.Screen()
    else:
        screen = urwid.raw_display.Screen()

    def unhandled(key):
        if key == 'f8':
            raise urwid.ExitMainLoop()

    urwid.MainLoop(frame, palette, screen,
        unhandled_input=unhandled).run()

def setup():
    urwid.web_display.set_preferences("Urwid Tour")
    # try to handle short web requests quickly
    if urwid.web_display.handle_short_request():
        return

    main()

if '__main__'==__name__ or urwid.web_display.is_web_request():
    setup()
