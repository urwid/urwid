"""Type checker fixture for the classes built by delegate_to_widget_mixin().

mypy and Pyrefly check this module; nothing in it runs.
The lines carrying an ignore pin a checker-visible behaviour: once the behaviour changes, the ignore is unused and
mypy's warn_unused_ignores fails the check.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    class Renamed(urwid.WidgetWrap[urwid.Edit]):
        """Subclass that renames the coordinates and widens the column, chaining through super()."""

        def rows(self, size: tuple[int], focus: bool = False) -> int:
            return super().rows(size, focus=focus)

        def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:  # type: ignore[override]
            return super().render(size, focus=focus)

        def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int] | None:
            return super().get_cursor_coords(size)

        def get_pref_col(self, size: tuple[int]) -> int | None:
            return super().get_pref_col(size)

        def move_cursor_to_coords(self, size: tuple[int], x: int | str, y: int) -> bool:
            if isinstance(x, str):
                return False
            return super().move_cursor_to_coords(size, x, y)

    class AttrMapThenLineBox(urwid.AttrMap[urwid.Text], urwid.LineBox[urwid.Text]):
        """Hybrid with the mixin before WidgetDecoration first."""

    class LineBoxThenAttrMap(urwid.LineBox[urwid.Text], urwid.AttrMap[urwid.Text]):
        """Hybrid with the mixin after WidgetDecoration first."""

    class PlaceholderThenWrap(urwid.WidgetPlaceholder[urwid.Text], urwid.WidgetWrap[urwid.Text]):
        """Hybrid of two classes that put the mixin before WidgetDecoration."""

    def forwarded(wrap: urwid.WidgetWrap[urwid.Edit]) -> None:
        assert_type(wrap.selectable(), bool)
        assert_type(wrap.sizing(), frozenset[urwid.Sizing])
        assert_type(wrap.pack((10,), focus=True), tuple[int, int])
        assert_type(wrap.rows((10,), focus=True), int)
        assert_type(wrap.keypress((10,), "x"), str | None)
        assert_type(wrap.mouse_event((10,), "mouse press", 1, 0, 0, focus=True), bool | None)
        assert_type(wrap.render((10,), focus=True), urwid.Canvas)
        assert_type(wrap.get_cursor_coords((10,)), tuple[int, int] | None)
        assert_type(wrap.get_pref_col((10,)), int | None)
        assert_type(wrap.move_cursor_to_coords((10,), 0, 0), bool)
        saved = wrap.pack
        assert_type(saved((10,)), tuple[int, int])

    def hybrids(first: AttrMapThenLineBox, second: LineBoxThenAttrMap, third: PlaceholderThenWrap) -> None:
        assert_type(first.render((10,)), urwid.CompositeCanvas)
        assert_type(second.render((10,)), urwid.CompositeCanvas)
        assert_type(third.render((10,)), urwid.Canvas)

    def containers() -> None:
        urwid.Columns([urwid.Button("a"), urwid.CheckBox("b"), urwid.AttrMap(urwid.Text("c"), None)])
        urwid.ListBox([urwid.Button("a"), urwid.RadioButton([], "b")])

    # Accepted break: a subclass that narrows size gets the mypy override error a subclass of Text already gets.
    class Narrowed(urwid.WidgetWrap[urwid.Text]):
        def keypress(self, size: tuple[int], key: str) -> str | None:  # type: ignore[override]
            return super().keypress(size, key)

    # Accepted break: render() returns Canvas, so methods that only CompositeCanvas has are not visible.
    def render_is_canvas() -> None:
        # pyrefly: ignore[missing-attribute]
        urwid.LineBox(urwid.Text("x")).render((10,)).trim(1)  # type: ignore[attr-defined]
        # pyrefly: ignore[missing-attribute]
        urwid.WidgetWrap(urwid.Text("x")).render((10,)).trim(1)  # type: ignore[attr-defined]

    # Accepted break: these classes are no longer assignable to unrelated types.
    def not_any() -> None:
        # pyrefly: ignore[bad-assignment]
        number: int = urwid.Button("x")  # type: ignore[assignment]
        assert_type(number, int)
