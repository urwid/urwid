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

if typing.TYPE_CHECKING:
    from collections.abc import Callable


class SwitchingPadding(urwid.Padding[urwid.BigText]):
    """Padding that switches its alignment based on the available width."""

    def padding_values(
        self,
        size: tuple[int],  # type: ignore[override]
        focus: bool,
    ) -> tuple[int, int]:
        """Return the left and right padding, aligning left or right depending on the available width.

        :param size: render size passed by the parent widget
        :param focus: whether the wrapped widget is in focus
        :returns: left and right padding widths
        """
        maxcol = size[0]
        width, _height = self.original_widget.pack((), focus=focus)  # urwid.BigText is FIXED size widget
        if maxcol > width:
            self.align = urwid.LEFT
        else:
            self.align = urwid.RIGHT
        return super().padding_values(size, focus)


class BigTextDisplay:
    """Interactive demo application for the :class:`urwid.BigText` widget."""

    palette: typing.ClassVar[list[tuple[str, str, str] | tuple[str, str, str, str]]] = [
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
    ) -> urwid.AttrMap[urwid.RadioButton]:
        """Create a radio button for selecting a font.

        :param g: radio button group to add the new button to
        :param name: label for the radio button
        :param font: font this button selects
        :param fn: callback connected to the button's ``change`` signal
        :returns: the radio button wrapped in an :class:`urwid.AttrMap`
        """
        w = urwid.RadioButton(g, name, False, on_state_change=fn)
        w.font = font
        w = urwid.AttrMap(w, "button normal", "button select")
        return w

    def create_disabled_radio_button(self, name: str) -> urwid.AttrMap[urwid.Text]:
        """Create a disabled placeholder shown for fonts unavailable in the current encoding mode.

        :param name: name of the unavailable font
        :returns: the placeholder text wrapped in an :class:`urwid.AttrMap`
        """
        w = urwid.Text(f"    {name} (UTF-8 mode required)")
        w = urwid.AttrMap(w, "button disabled")
        return w

    def create_edit(
        self,
        label: str,
        text: str,
        fn: Callable[[urwid.Edit, str], typing.Any],
    ) -> urwid.AttrMap[urwid.Edit]:
        """Create an edit widget and connect it to a change callback.

        :param label: caption shown before the editable text
        :param text: initial contents of the edit widget
        :param fn: callback connected to the widget's ``change`` signal, also invoked immediately
        :returns: the edit widget wrapped in an :class:`urwid.AttrMap`
        """
        w = urwid.Edit(label, text)
        urwid.connect_signal(w, "change", fn)
        fn(w, text)
        w = urwid.AttrMap(w, "edit")
        return w

    def set_font_event(self, w: urwid.RadioButton, state: bool) -> None:
        """Switch the displayed :class:`urwid.BigText` to the selected font.

        :param w: radio button whose state changed, carrying the ``font`` it selects
        :param state: new state of the radio button
        """
        if state:
            self.bigtext.set_font(w.font)
            self.chars_avail.set_text(w.font.characters())

    def edit_change_event(self, widget: urwid.Edit, text: str) -> None:
        """Update the :class:`urwid.BigText` display with the edited text.

        :param widget: edit widget that changed
        :param text: new contents of the edit widget
        """
        self.bigtext.set_text(text)

    def setup_view(
        self,
    ) -> tuple[
        urwid.Frame[urwid.AttrMap[urwid.ListBox[int]], urwid.AttrMap[urwid.Text], None],
        urwid.Overlay[urwid.BigText, urwid.Frame[urwid.AttrMap[urwid.ListBox[int]], urwid.AttrMap[urwid.Text], None]],
    ]:
        """Build the main view and the exit-confirmation overlay.

        :returns: the main frame, and an overlay of the exit prompt on top of that frame
        """
        fonts = urwid.get_all_fonts()
        # setup mode radio buttons
        self.font_buttons: list[urwid.AttrMap[urwid.RadioButton] | urwid.AttrMap[urwid.Text]] = []
        group: list[urwid.RadioButton] = []
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
        self.bigtext = urwid.BigText("", None)  # type: ignore[arg-type]  # font assigned before render
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
        fonts_pile = urwid.Pile([urwid.Text("Fonts:"), *self.font_buttons], focus_item=1)
        col = urwid.Columns([(16, chars), fonts_pile], 3, focus_column=1)
        bt_pile = urwid.Pile([bt, edit], focus_item=1)
        lines: list[urwid.widget.AbstractFlowWidget] = [bt_pile, urwid.Divider(), col]
        listbox = urwid.ListBox(urwid.SimpleListWalker(lines))

        # Frame
        w: urwid.Frame[
            urwid.AttrMap[urwid.ListBox[int]],
            urwid.AttrMap[urwid.Text],
            None,
        ] = urwid.Frame(
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

    def main(self) -> None:
        """Build the view and run the main loop until the user exits."""
        self.view, self.exit_view = self.setup_view()
        self.loop = urwid.MainLoop(self.view, self.palette, unhandled_input=self.unhandled_input)
        self.loop.run()

    def unhandled_input(self, key: str | tuple[str, int, int, int]) -> bool | None:
        """Handle keys not consumed by the widgets: :kbd:`f8` to confirm exit, :kbd:`y`/:kbd:`n` to answer it.

        :param key: unhandled key or mouse event
        :returns: ``True`` if the key was handled, ``None`` otherwise
        :raises urwid.ExitMainLoop: when the user confirms the exit prompt with :kbd:`y`
        """
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


def main() -> None:
    """Run the BigText example program."""
    BigTextDisplay().main()


if __name__ == "__main__":
    main()
