"""Type checker fixture for the FilteredListWalker list walker.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from typing import assert_type

    import urwid

    def filtered_list_walker() -> None:
        """Type the view over a list walker, a deque walker and a plain list."""
        source = urwid.SimpleFocusListWalker([urwid.Text("apple"), urwid.Text("pear")])
        view = urwid.FilteredListWalker(source, predicate=lambda widget: widget.text == "pear")
        assert_type(view.get_focus(), tuple[urwid.Text, int] | tuple[None, None])
        assert_type(view.positions(), Iterator[int])
        assert_type(view.positions(reverse=True), Iterator[int])
        assert_type(view.source, Sequence[urwid.Text])
        assert_type(view.predicate, Callable[[urwid.Text], bool] | None)
        assert_type(view[0], urwid.Text)
        view.predicate = None
        view.set_predicate(lambda widget: bool(widget.text))
        view.refilter()
        urwid.ListBox(view)

        deque_source = urwid.SimpleFocusDequeWalker([urwid.Text("line")], maxlen=100)
        deque_view = urwid.FilteredListWalker(deque_source, wrap_around=True)
        assert_type(deque_view.source, Sequence[urwid.Text])

        list_view = urwid.FilteredListWalker([urwid.Button("ok")])
        assert_type(list_view.get_focus(), tuple[urwid.Button, int] | tuple[None, None])
