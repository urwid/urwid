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
# Urwid web site: https://urwid.org/

"""
Urwid tour.  Shows many of the standard widget types and features.
"""

from __future__ import annotations

import urwid


def main():
    text_header = "Welcome to the urwid tour!  UP / DOWN / PAGE UP / PAGE DOWN scroll.  F8 exits."
    text_intro = [
        ("important", "Text"),
        " widgets are the most common in "
        "any urwid program.  This Text widget was created "
        "without setting the wrap or align mode, so it "
        "defaults to left alignment with wrapping on space "
        "characters.  ",
        ("important", "Change the window width"),
        " to see how the widgets on this page react.  This Text widget is wrapped with a ",
        ("important", "Padding"),
        " widget to keep it indented on the left and right.",
    ]
    text_right = "This Text widget is right aligned.  Wrapped words stay to the right as well. "
    text_center = "This one is center aligned."
    text_clip = (
        "Text widgets may be clipped instead of wrapped.\n"
        "Extra text is discarded instead of wrapped to the next line. "
        "65-> 70-> 75-> 80-> 85-> 90-> 95-> 100>\n"
        "Newlines embedded in the string are still respected."
    )
    text_right_clip = (
        "This is a right aligned and clipped Text widget.\n"
        "<100 <-95 <-90 <-85 <-80 <-75 <-70 <-65             "
        "Text will be cut off at the left of this widget."
    )
    text_center_clip = "Center aligned and clipped widgets will have text cut off both sides."
    text_ellipsis = (
        "Text can be clipped using the ellipsis character (…)\n"
        "Extra text is discarded and a … mark is shown."
        "50-> 55-> 60-> 65-> 70-> 75-> 80-> 85-> 90-> 95-> 100>\n"
    )
    text_any = (
        "The 'any' wrap mode will wrap on any character.  This "
        "mode will not collapse space characters at the end of the "
        "line but it still honors embedded newline characters.\n"
        "Like this one."
    )
    text_padding = (
        "Padding widgets have many options.  This "
        "is a standard Text widget wrapped with a Padding widget "
        "with the alignment set to relative 20% and with its width "
        "fixed at 40."
    )
    text_divider = [
        "The ",
        ("important", "Divider"),
        " widget repeats the same character across the whole line.  It can also add blank lines above and below.",
    ]
    text_edit = [
        "The ",
        ("important", "Edit"),
        " widget is a simple text editing widget.  It supports cursor "
        "movement and tries to maintain the current column when focus "
        "moves to another edit widget.  It wraps and aligns the same "
        "way as Text widgets.",
    ]
    text_edit_cap1 = ("editcp", "This is a caption.  Edit here: ")
    text_edit_text1 = "editable stuff"
    text_edit_cap2 = ("editcp", "This one supports newlines: ")
    text_edit_text2 = (
        "line one starts them all\n"
        "== line 2 == with some more text to edit.. words.. whee..\n"
        "LINE III, the line to end lines one and two, unless you "
        "change something."
    )
    text_edit_cap3 = ("editcp", "This one is clipped, try editing past the edge: ")
    text_edit_text3 = "add some text here -> -> -> ...."
    text_edit_alignments = "Different Alignments:"
    text_edit_left = "left aligned (default)"
    text_edit_center = "center aligned"
    text_edit_right = "right aligned"
    text_intedit = ("editcp", [("important", "IntEdit"), " allows only numbers: "])
    text_edit_padding = ("editcp", "Edit widget within a Padding widget ")
    text_columns1 = [
        ("important", "Columns"),
        " are used to share horizontal screen space.  "
        "This one splits the space into two parts with "
        "three characters between each column.  The "
        "contents of each column is a single widget.",
    ]
    text_columns2 = [
        "When you need to put more than one widget into a column you can use a ",
        ("important", "Pile"),
        " to combine two or more widgets.",
    ]
    text_col_columns = "Columns may be placed inside other columns."
    text_col_21 = "Col 2.1"
    text_col_22 = "Col 2.2"
    text_col_23 = "Col 2.3"
    text_column_widths = (
        "Columns may also have uneven relative "
        "weights or fixed widths.  Use a minimum width so that "
        "columns don't become too small."
    )
    text_weight = "Weight %d"
    text_fixed_9 = "<Fixed 9>"  # should be 9 columns wide
    text_fixed_14 = "<--Fixed 14-->"  # should be 14 columns wide
    text_edit_col_cap1 = ("editcp", "Edit widget within Columns")
    text_edit_col_text1 = "here's\nsome\ninfo"
    text_edit_col_cap2 = ("editcp", "and within Pile ")
    text_edit_col_text2 = "more"
    text_edit_col_cap3 = ("editcp", "another ")
    text_edit_col_text3 = "still more"
    text_gridflow = [
        "A ",
        ("important", "GridFlow"),
        " widget "
        "may be used to display a list of flow widgets with equal "
        "widths.  Widgets that don't fit on the first line will "
        "flow to the next.  This is useful for small widgets that "
        "you want to keep together such as ",
        ("important", "Button"),
        ", ",
        ("important", "CheckBox"),
        " and ",
        ("important", "RadioButton"),
        " widgets.",
    ]
    text_button_list = ["Yes", "No", "Perhaps", "Certainly", "Partially", "Tuesdays Only", "Help"]
    text_cb_list = ["Wax", "Wash", "Buff", "Clear Coat", "Dry", "Racing Stripe"]
    text_rb_list = ["Morning", "Afternoon", "Evening", "Weekend"]
    text_listbox = [
        "All these widgets have been displayed with the help of a ",
        ("important", "ListBox"),
        " widget.  ListBox widgets handle scrolling and changing focus.  A ",
        ("important", "Frame"),
        " widget is used to keep the instructions at the top of the screen.",
    ]

    def button_press(button):
        frame.footer = urwid.AttrMap(urwid.Text(["Pressed: ", button.get_label()]), "header")

    radio_button_group = []

    blank = urwid.Divider()
    listbox_content = [
        blank,
        urwid.Padding(urwid.Text(text_intro), left=2, right=2, min_width=20),
        blank,
        urwid.Text(text_right, align=urwid.RIGHT),
        blank,
        urwid.Text(text_center, align=urwid.CENTER),
        blank,
        urwid.Text(text_clip, wrap=urwid.CLIP),
        blank,
        urwid.Text(text_right_clip, align=urwid.RIGHT, wrap=urwid.CLIP),
        blank,
        urwid.Text(text_center_clip, align=urwid.CENTER, wrap=urwid.CLIP),
        blank,
        urwid.Text(text_ellipsis, wrap=urwid.ELLIPSIS),
        blank,
        urwid.Text(text_any, wrap=urwid.ANY),
        blank,
        urwid.Padding(urwid.Text(text_padding), (urwid.RELATIVE, 20), 40),
        blank,
        urwid.AttrMap(urwid.Divider("=", 1), "bright"),
        urwid.Padding(urwid.Text(text_divider), left=2, right=2, min_width=20),
        urwid.AttrMap(urwid.Divider("-", 0, 1), "bright"),
        blank,
        urwid.Padding(urwid.Text(text_edit), left=2, right=2, min_width=20),
        blank,
        urwid.AttrMap(urwid.Edit(text_edit_cap1, text_edit_text1), "editbx", "editfc"),
        blank,
        urwid.AttrMap(urwid.Edit(text_edit_cap2, text_edit_text2, multiline=True), "editbx", "editfc"),
        blank,
        urwid.AttrMap(urwid.Edit(text_edit_cap3, text_edit_text3, wrap=urwid.CLIP), "editbx", "editfc"),
        blank,
        urwid.Text(text_edit_alignments),
        urwid.AttrMap(urwid.Edit("", text_edit_left, align=urwid.LEFT), "editbx", "editfc"),
        urwid.AttrMap(urwid.Edit("", text_edit_center, align=urwid.CENTER), "editbx", "editfc"),
        urwid.AttrMap(urwid.Edit("", text_edit_right, align=urwid.RIGHT), "editbx", "editfc"),
        blank,
        urwid.AttrMap(urwid.IntEdit(text_intedit, 123), "editbx", "editfc"),
        blank,
        urwid.Padding(urwid.AttrMap(urwid.Edit(text_edit_padding, ""), "editbx", "editfc"), left=10, width=50),
        blank,
        blank,
        urwid.AttrMap(
            urwid.Columns(
                [
                    urwid.Divider("."),
                    urwid.Divider(","),
                    urwid.Divider("."),
                ]
            ),
            "bright",
        ),
        blank,
        urwid.Columns(
            [
                urwid.Padding(urwid.Text(text_columns1), left=2, right=0, min_width=20),
                urwid.Pile([urwid.Divider("~"), urwid.Text(text_columns2), urwid.Divider("_")]),
            ],
            3,
        ),
        blank,
        blank,
        urwid.Columns(
            [
                urwid.Text(text_col_columns),
                urwid.Columns(
                    [
                        urwid.Text(text_col_21),
                        urwid.Text(text_col_22),
                        urwid.Text(text_col_23),
                    ],
                    1,
                ),
            ],
            2,
        ),
        blank,
        urwid.Padding(urwid.Text(text_column_widths), left=2, right=2, min_width=20),
        blank,
        urwid.Columns(
            [
                urwid.AttrMap(urwid.Text(text_weight % 1), "reverse"),
                (urwid.WEIGHT, 2, urwid.Text(text_weight % 2)),
                (urwid.WEIGHT, 3, urwid.AttrMap(urwid.Text(text_weight % 3), "reverse")),
                (urwid.WEIGHT, 4, urwid.Text(text_weight % 4)),
                (urwid.WEIGHT, 5, urwid.AttrMap(urwid.Text(text_weight % 5), "reverse")),
                (urwid.WEIGHT, 6, urwid.Text(text_weight % 6)),
            ],
            0,
            min_width=8,
        ),
        blank,
        urwid.Columns(
            [
                (urwid.WEIGHT, 2, urwid.AttrMap(urwid.Text(text_weight % 2), "reverse")),
                (9, urwid.Text(text_fixed_9)),
                (urwid.WEIGHT, 3, urwid.AttrMap(urwid.Text(text_weight % 3), "reverse")),
                (14, urwid.Text(text_fixed_14)),
            ],
            0,
            min_width=8,
        ),
        blank,
        urwid.Columns(
            [
                urwid.AttrMap(urwid.Edit(text_edit_col_cap1, text_edit_col_text1, multiline=True), "editbx", "editfc"),
                urwid.Pile(
                    [
                        urwid.AttrMap(urwid.Edit(text_edit_col_cap2, text_edit_col_text2), "editbx", "editfc"),
                        blank,
                        urwid.AttrMap(urwid.Edit(text_edit_col_cap3, text_edit_col_text3), "editbx", "editfc"),
                    ]
                ),
            ],
            1,
        ),
        blank,
        urwid.AttrMap(
            urwid.Columns(
                [
                    urwid.Divider("'"),
                    urwid.Divider('"'),
                    urwid.Divider("~"),
                    urwid.Divider('"'),
                    urwid.Divider("'"),
                ]
            ),
            "bright",
        ),
        blank,
        blank,
        urwid.Padding(urwid.Text(text_gridflow), left=2, right=2, min_width=20),
        blank,
        urwid.Padding(
            urwid.GridFlow(
                [urwid.AttrMap(urwid.Button(txt, button_press), "buttn", "buttnf") for txt in text_button_list],
                13,
                3,
                1,
                urwid.LEFT,
            ),
            left=4,
            right=3,
            min_width=13,
        ),
        blank,
        urwid.Padding(
            urwid.GridFlow(
                [urwid.AttrMap(urwid.CheckBox(txt), "buttn", "buttnf") for txt in text_cb_list],
                10,
                3,
                1,
                urwid.LEFT,
            ),
            left=4,
            right=3,
            min_width=10,
        ),
        blank,
        urwid.Padding(
            urwid.GridFlow(
                [urwid.AttrMap(urwid.RadioButton(radio_button_group, txt), "buttn", "buttnf") for txt in text_rb_list],
                13,
                3,
                1,
                urwid.LEFT,
            ),
            left=4,
            right=3,
            min_width=13,
        ),
        blank,
        blank,
        urwid.Padding(urwid.Text(text_listbox), left=2, right=2, min_width=20),
        blank,
        blank,
    ]

    header = urwid.AttrMap(urwid.Text(text_header), "header")
    listbox = urwid.ListBox(urwid.SimpleListWalker(listbox_content))
    scrollable = urwid.ScrollBar(
        listbox,
        trough_char=urwid.ScrollBar.Symbols.LITE_SHADE,
    )
    frame = urwid.Frame(urwid.AttrMap(scrollable, "body"), header=header)

    palette = [
        ("body", "black", "light gray", "standout"),
        ("reverse", "light gray", "black"),
        ("header", "white", "dark red", "bold"),
        ("important", "dark blue", "light gray", ("standout", "underline")),
        ("editfc", "white", "dark blue", "bold"),
        ("editbx", "light gray", "dark blue"),
        ("editcp", "black", "light gray", "standout"),
        ("bright", "dark gray", "light gray", ("bold", "standout")),
        ("buttn", "black", "dark cyan"),
        ("buttnf", "white", "dark blue", "bold"),
    ]

    # use appropriate Screen class
    if urwid.display.web.is_web_request():
        screen = urwid.display.web.Screen()
    else:
        screen = urwid.display.raw.Screen()

    def unhandled(key: str | tuple[str, int, int, int]) -> None:
        if key == "f8":
            raise urwid.ExitMainLoop()

    urwid.MainLoop(frame, palette, screen, unhandled_input=unhandled).run()


def setup():
    urwid.display.web.set_preferences("Urwid Tour")
    # try to handle short web requests quickly
    if urwid.display.web.handle_short_request():
        return

    main()


if __name__ == "__main__" or urwid.display.web.is_web_request():
    setup()
