#!/usr/bin/env python
#
# Urwid BigText example program
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
Urwid example demonstrating use of the BigText widget.
"""

from __future__ import annotations

import typing

import urwid
import urwid.display.raw

if typing.TYPE_CHECKING:
    from collections.abc import Callable


_Wrapped = typing.TypeVar("_Wrapped")


class SwitchingPadding(urwid.Padding[_Wrapped]):
    def padding_values(self, size, focus: bool) -> tuple[int, int]:
        maxcol = size[0]
        width, _height = self.original_widget.pack(size, focus=focus)
        if maxcol > width:
            self.align = urwid.LEFT
        else:
            self.align = urwid.RIGHT
        return super().padding_values(size, focus)


class BigTextDisplay:
    palette: typing.ClassVar[list[tuple[str, str, str, ...]]] = [
        ("body", "black", "light gray", "standout"),
        ("header", "white", "dark red", "bold"),
        ("button normal", "light gray", "dark blue", "standout"),
        ("button select", "white", "dark green"),
        ("button disabled", "dark gray", "dark blue"),
        ("edit", "light gray", "dark blue"),
        ("bigtext", "white", "black"),
        ("chars", "light gray", "black"),
        ("exit", "white", "dark cyan"),
    ]

    def create_radio_button(
        self,
        g: list[urwid.RadioButton],
        name: str,
        font: urwid.Font,
        fn: Callable[[urwid.RadioButton, bool], typing.Any],
    ) -> urwid.AttrMap:
        w = urwid.RadioButton(g, name, False, on_state_change=fn)
        w.font = font
        w = urwid.AttrMap(w, "button normal", "button select")
        return w

    def create_disabled_radio_button(self, name: str) -> urwid.AttrMap:
        w = urwid.Text(f"    {name} (UTF-8 mode required)")
        w = urwid.AttrMap(w, "button disabled")
        return w

    def create_edit(
        self,
        label: str,
        text: str,
        fn: Callable[[urwid.Edit, str], typing.Any],
    ) -> urwid.AttrMap:
        w = urwid.Edit(label, text)
        urwid.connect_signal(w, "change", fn)
        fn(w, text)
        w = urwid.AttrMap(w, "edit")
        return w

    def set_font_event(self, w, state: bool) -> None:
        if state:
            self.bigtext.set_font(w.font)
            self.chars_avail.set_text(w.font.characters())

    def edit_change_event(self, widget, text: str) -> None:
        self.bigtext.set_text(text)

    def setup_view(
        self,
    ) -> tuple[
        urwid.Frame[urwid.AttrMap[urwid.ListBox], urwid.AttrMap[urwid.Text], None],
        urwid.Overlay[urwid.BigText, urwid.Frame[urwid.AttrMap[urwid.ListBox], urwid.AttrMap[urwid.Text], None]],
    ]:
        fonts = urwid.get_all_fonts()
        # setup mode radio buttons
        self.font_buttons = []
        group = []
        utf8 = urwid.get_encoding_mode() == "utf8"
        for name, fontcls in fonts:
            font = fontcls()
            if font.utf8_required and not utf8:
                rb = self.create_disabled_radio_button(name)
            else:
                rb = self.create_radio_button(group, name, font, self.set_font_event)
                if fontcls == urwid.Thin6x6Font:
                    chosen_font_rb = rb
                    exit_font = font
            self.font_buttons.append(rb)

        # Create BigText
        self.bigtext = urwid.BigText("", None)
        bt = urwid.BoxAdapter(
            urwid.Filler(
                urwid.AttrMap(
                    SwitchingPadding(self.bigtext, urwid.LEFT, None),
                    "bigtext",
                ),
                urwid.BOTTOM,
                None,
                7,
            ),
            7,
        )

        # Create chars_avail
        cah = urwid.Text("Characters Available:")
        self.chars_avail = urwid.Text("", wrap=urwid.ANY)
        ca = urwid.AttrMap(self.chars_avail, "chars")

        chosen_font_rb.original_widget.set_state(True)  # causes set_font_event call

        # Create Edit widget
        edit = self.create_edit("", "Urwid BigText example", self.edit_change_event)

        # ListBox
        chars = urwid.Pile([cah, ca])
        fonts = urwid.Pile([urwid.Text("Fonts:"), *self.font_buttons], focus_item=1)
        col = urwid.Columns([(16, chars), fonts], 3, focus_column=1)
        bt = urwid.Pile([bt, edit], focus_item=1)
        lines = [bt, urwid.Divider(), col]
        listbox = urwid.ListBox(urwid.SimpleListWalker(lines))

        # Frame
        w = urwid.Frame(
            body=urwid.AttrMap(listbox, "body"),
            header=urwid.AttrMap(urwid.Text("Urwid BigText example program - F8 exits."), "header"),
        )

        # Exit message
        exit_w = urwid.Overlay(
            urwid.BigText(("exit", " Quit? "), exit_font),
            w,
            urwid.CENTER,
            None,
            urwid.MIDDLE,
            None,
        )
        return w, exit_w

    def main(self):
        self.view, self.exit_view = self.setup_view()
        self.loop = urwid.MainLoop(self.view, self.palette, unhandled_input=self.unhandled_input)
        self.loop.run()

    def unhandled_input(self, key: str | tuple[str, int, int, int]) -> bool | None:
        if key == "f8":
            self.loop.widget = self.exit_view
            return True
        if self.loop.widget != self.exit_view:
            return None
        if key in {"y", "Y"}:
            raise urwid.ExitMainLoop()
        if key in {"n", "N"}:
            self.loop.widget = self.view
            return True
        return None


def main():
    BigTextDisplay().main()


if __name__ == "__main__":
    main()
