#!/usr/bin/env python

from __future__ import annotations

import typing

import urwid

if typing.TYPE_CHECKING:
    from urwid.widget.popup import PopUpParametersModel


class PopUpDialog(urwid.WidgetWrap[urwid.AttrMap[urwid.Filler[urwid.Pile]]]):
    """A dialog that appears with nothing but a close button"""

    signals: typing.ClassVar[list[str]] = ["close"]

    def __init__(self) -> None:
        close_button = urwid.Button("that's pretty cool")
        urwid.connect_signal(close_button, "click", lambda button: self._emit("close"))
        pile = urwid.Pile(
            [
                urwid.Text("^^  I'm attached to the widget that opened me. Try resizing the window!\n"),
                close_button,
            ]
        )
        super().__init__(urwid.AttrMap(urwid.Filler(pile), "popbg"))


class ThingWithAPopUp(urwid.PopUpLauncher[urwid.Button]):
    """A button that opens a :class:`PopUpDialog` when clicked."""

    def __init__(self) -> None:
        super().__init__(urwid.Button("click-me"))
        urwid.connect_signal(self.original_widget, "click", lambda button: self.open_pop_up())

    def create_pop_up(self) -> PopUpDialog:
        """Return a new pop-up dialog wired to close itself on click."""
        pop_up = PopUpDialog()
        urwid.connect_signal(pop_up, "close", lambda button: self.close_pop_up())
        return pop_up

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Return the position and size of the pop-up relative to this widget."""
        return {"left": 0, "top": 1, "overlay_width": 32, "overlay_height": 7}

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Handle a keypress, exiting the program on :kbd:`q` or :kbd:`Q`.

        :raises urwid.ExitMainLoop: when the pressed key is :kbd:`q` or :kbd:`Q`.
        """
        parsed = super().keypress(size, key)
        if parsed in {"q", "Q"}:
            raise urwid.ExitMainLoop("Done")
        return parsed


fill = urwid.Filler(urwid.Padding(ThingWithAPopUp(), urwid.CENTER, 15))
loop = urwid.MainLoop(fill, [("popbg", "white", "dark blue")], pop_ups=True)
loop.run()
