#!/usr/bin/env python

"""Example: a list that narrows as a filter query is typed.

Letters edit the query, which shows the words that contain it, and a click on a word picks it.
Up, down, page up, page down, home and end move in the list while the cursor stays in the query,
enter picks the word in focus, and esc exits.
"""

from __future__ import annotations

import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable

# Pairs of these syllables make a few hundred words to filter.
SYLLABLES = ("ba", "ce", "di", "fo", "gu", "ka", "le", "mi", "no", "pu", "ra", "se", "ti", "vo", "ya", "zu", "xe")
LIST_KEYS = frozenset({"up", "down", "page up", "page down", "home", "end", "enter"})
HELP = "arrows, page up/down, home/end: move  enter: pick  esc: quit"


class FilterFrame(urwid.Frame[urwid.ListBox[int], urwid.Edit, urwid.Text]):
    """Frame with the query in focus that sends the list keys to the list.

    The keys go to the list before the query sees them,
    because an ``Edit`` handles home and end, and up and down while its text wraps.
    """

    def __init__(self, listbox: urwid.ListBox[int], query: urwid.Edit, status: urwid.Text) -> None:
        """Show *query* above *listbox* and *status* below it, with the focus in *query*.

        On a short screen the list keeps 3 rows before the status line, which wraps on a narrow one.
        """
        super().__init__(listbox, header=query, footer=status, focus_part="header", min_body_rows=3)
        self._query = query

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # type: ignore[override]
        """Send a list key to the list, sized as it is drawn, and every other key to the query."""
        if key not in LIST_KEYS:
            return self._query.keypress((size[0],), key)
        maxcol, maxrow = size
        (hrows, frows), _ = self.frame_top_bottom(size, True)
        remaining = maxrow - hrows - frows
        if remaining <= 0 or not self.body.selectable():
            return key
        return self.body.keypress((maxcol, remaining), key)

    def mouse_event(  # type: ignore[override]
        self,
        size: tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Handle a click as a frame does, then put the focus back in the query, where the typed keys go."""
        handled = super().mouse_event(size, event, button, col, row, focus)
        self.focus_position = "header"
        return handled


def text_matches(query: str) -> Callable[[urwid.Button], bool] | None:
    """Return a predicate that matches buttons whose label contains *query*, or ``None`` for an empty query."""
    if not query:
        return None
    folded = query.casefold()
    return lambda button: folded in str(button.label).casefold()


def main() -> None:
    """Build the query, the filtered list and the status line, and run the main loop."""
    status = urwid.Text(HELP)
    buttons = [urwid.Button(first + second) for first in SYLLABLES for second in SYLLABLES]
    view = urwid.FilteredListWalker(urwid.SimpleFocusListWalker(buttons))
    query = urwid.Edit("Filter: ")

    def picked(button: urwid.Button) -> None:
        status.set_text(f"picked {button.label}  {HELP}")

    def query_changed(_edit: urwid.Edit, _old: str) -> None:
        view.set_predicate(text_matches(query.edit_text))

    for button in buttons:
        urwid.connect_signal(button, "click", picked)
    urwid.connect_signal(query, "postchange", query_changed)
    frame = FilterFrame(urwid.ListBox(view), query, status)

    def unhandled(key: str | tuple[str, int, int, int]) -> None:
        if key == "esc":
            raise urwid.ExitMainLoop

    urwid.MainLoop(frame, unhandled_input=unhandled).run()


if __name__ == "__main__":
    main()
