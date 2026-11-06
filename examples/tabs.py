#!/usr/bin/env python

"""Example: a tabbed window with a status line, where tabs can be switched and closed.

META RIGHT / META LEFT or a mouse click switch tabs, UP from a body moves to the tab labels,
CTRL W closes the current tab, and the program exits when the last tab is closed or on F8.
"""

from __future__ import annotations

import urwid
from urwid.command_map import Command


def main() -> None:
    """Build the tabs, the status line and the key handling, and run the main loop."""
    tabs = urwid.Tabs(
        [
            ("Files", urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Button(f"file {n}.txt") for n in range(30)]))),
            ("Form", urwid.Filler(urwid.Pile([urwid.Edit("Name: "), urwid.Edit("Mail: ")]), valign="top")),
            ("About", urwid.Filler(urwid.Text("Tabs example: one row of labels over the selected body."))),
        ],
        bar_selectable=True,
        underline=(urwid.Tabs.Symbols.LINE_LIGHT, urwid.Tabs.Symbols.LINE_HEAVY),
        attr_map="tab",
        selected_map="tab selected",
        focus_map="tab cursor",
    )
    status = urwid.Text("")

    def update_status(*_args: object) -> None:
        # Read `focus` first: the signal for closing the last tab arrives when the widget is already empty.
        if tabs.focus is None:
            status.set_text("no tabs")
            return
        label = tabs.contents[tabs.focus_position][1].render(()).decoded_text[0]
        status.set_text(f"tab {tabs.focus_position + 1} of {len(tabs)}: {label}")

    urwid.connect_signal(tabs, "focus changed", update_status)
    update_status()

    def unhandled(key: str | tuple[str, int, int, int]) -> None:
        if key == "f8":
            raise urwid.ExitMainLoop
        if key == "ctrl w" and tabs.contents:
            del tabs.contents[tabs.focus_position]
            # Closing a tab other than the last keeps the index, which sends no "focus changed".
            update_status()
            if not tabs.contents:
                raise urwid.ExitMainLoop

    urwid.command_map.bind(Command.NEXT_TAB, "meta right")
    urwid.command_map.bind(Command.PREVIOUS_TAB, "meta left")
    frame: urwid.Frame[urwid.Tabs, None, urwid.AttrMap[urwid.Text]] = urwid.Frame(
        tabs,
        footer=urwid.AttrMap(status, "status"),
    )
    palette: list[tuple[str, str, str] | tuple[str, str, str, str]] = [
        ("tab", "dark gray", ""),
        ("tab selected", "light blue", "", "bold"),
        ("tab cursor", "yellow", "dark blue", "bold"),
        ("status", "white", "dark red"),
    ]
    urwid.MainLoop(frame, palette, unhandled_input=unhandled).run()


if __name__ == "__main__":
    main()
