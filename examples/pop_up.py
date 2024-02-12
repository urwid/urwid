#!/usr/bin/env python

from __future__ import annotations

import typing

import urwid


class PopUpDialog(urwid.WidgetWrap):
    """A dialog that appears with nothing but a close button"""

    signals: typing.ClassVar[list[str]] = ["close"]

    def __init__(self):
        close_button = urwid.Button("that's pretty cool")
        urwid.connect_signal(close_button, "click", lambda button: self._emit("close"))
        pile = urwid.Pile(
            [
                urwid.Text("^^  I'm attached to the widget that opened me. Try resizing the window!\n"),
                close_button,
            ]
        )
        super().__init__(urwid.AttrMap(urwid.Filler(pile), "popbg"))


class ThingWithAPopUp(urwid.PopUpLauncher):
    def __init__(self) -> None:
        super().__init__(urwid.Button("click-me"))
        urwid.connect_signal(self.original_widget, "click", lambda button: self.open_pop_up())

    def create_pop_up(self) -> PopUpDialog:
        pop_up = PopUpDialog()
        urwid.connect_signal(pop_up, "close", lambda button: self.close_pop_up())
        return pop_up

    def get_pop_up_parameters(self):
        return {"left": 0, "top": 1, "overlay_width": 32, "overlay_height": 7}

    def keypress(self, size: tuple[int], key: str) -> str | None:
        parsed = super().keypress(size, key)
        if parsed in {"q", "Q"}:
            raise urwid.ExitMainLoop("Done")
        return parsed


fill = urwid.Filler(urwid.Padding(ThingWithAPopUp(), urwid.CENTER, 15))
loop = urwid.MainLoop(fill, [("popbg", "white", "dark blue")], pop_ups=True)
loop.run()
