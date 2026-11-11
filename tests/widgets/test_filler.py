from __future__ import annotations

import typing
import unittest
import warnings

import urwid
import urwid.testing
from tests.util import FocusHeightWidget, assert_attribute_redraws


class CursorWidget(urwid.Widget):
    """Minimal selectable widget with a scripted cursor, used to drive Filler's cursor-related methods."""

    def __init__(
        self,
        sizing: tuple[urwid.Sizing, ...],
        num_rows: int = 1,
        cursor: tuple[int, int] | None = (0, 0),
        move_result: bool = True,
        mouse_result: bool = True,
    ) -> None:
        super().__init__()
        self._sizing_set = frozenset(sizing)
        self.num_rows = num_rows
        self.cursor_pos = cursor
        self.move_result = move_result
        self.mouse_result = mouse_result
        #: The size each input and cursor method was called with, as ``(method name, size)``.
        self.sizes: list[tuple[str, tuple[int] | tuple[int, int]]] = []

    def sizing(self) -> frozenset[urwid.Sizing]:
        return self._sizing_set

    def selectable(self) -> bool:
        return True

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return self.num_rows

    def render(self, size: tuple[int, int] | tuple[int], focus: bool = False) -> urwid.TextCanvas:
        maxcol = size[0]
        maxrow = size[1] if len(size) == 2 else self.num_rows
        return urwid.TextCanvas([b" " * maxcol for _ in range(maxrow)], maxcol=maxcol)

    def keypress(self, size: tuple[int, int] | tuple[int], key: str) -> str | None:
        self.sizes.append(("keypress", size))

    def get_cursor_coords(self, size: tuple[int, int] | tuple[int]) -> tuple[int, int] | None:
        self.sizes.append(("get_cursor_coords", size))
        return self.cursor_pos

    def get_pref_col(self, size: tuple[int, int] | tuple[int]) -> int:
        self.sizes.append(("get_pref_col", size))
        return self.cursor_pos[0] if self.cursor_pos else 0

    def move_cursor_to_coords(self, size: tuple[int, int] | tuple[int], col: int, row: int) -> bool:
        self.sizes.append(("move_cursor_to_coords", size))
        return self.move_result

    def mouse_event(
        self,
        size: tuple[int, int] | tuple[int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool:
        self.sizes.append(("mouse_event", size))
        return self.mouse_result


class PlainBoxWidget(urwid.Widget):
    """A box widget without the optional cursor methods.

    :class:`urwid.Widget` does not define ``get_cursor_coords``, ``get_pref_col`` or ``move_cursor_to_coords``,
    so ``hasattr`` checks for them are ``False``.
    """

    _sizing = frozenset([urwid.BOX])

    def render(self, size: tuple[int, int], focus: bool = False) -> urwid.TextCanvas:
        maxcol, maxrow = size
        return urwid.TextCanvas([b" " * maxcol for _ in range(maxrow)], maxcol=maxcol)


class NonWidgetBox:
    """A box widget-like object that does not derive from :class:`urwid.Widget` and has no ``mouse_event``."""

    def sizing(self) -> frozenset[urwid.Sizing]:
        return frozenset((urwid.BOX,))

    def selectable(self) -> bool:
        return False

    def render(self, size: tuple[int, int], focus: bool = False) -> urwid.TextCanvas:
        maxcol, maxrow = size
        return urwid.TextCanvas([b" " * maxcol for _ in range(maxrow)], maxcol=maxcol)


class TrimWidget(urwid.Widget):
    """Flow widget rendering a fixed number of rows with an optional scripted cursor, for render() trim tests."""

    _sizing = frozenset([urwid.FLOW])

    def __init__(self, num_rows: int, cursor: tuple[int, int] | None = None) -> None:
        super().__init__()
        self.num_rows = num_rows
        self.cursor_pos = cursor

    def selectable(self) -> bool:
        return True

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return self.num_rows

    def render(self, size: tuple[int], focus: bool = False) -> urwid.TextCanvas:
        maxcol = size[0]
        cursor = self.cursor_pos if focus else None
        return urwid.TextCanvas([b" " * maxcol for _ in range(self.num_rows)], maxcol=maxcol, cursor=cursor)

    def keypress(self, size: tuple[int], key: str) -> str | None:
        return None


class FlowOnlyRenderWidget(urwid.Widget):
    """A widget that reports BOX and FLOW sizing but renders only at a flow size, one digit per row."""

    _sizing = frozenset([urwid.BOX, urwid.FLOW])

    def __init__(self, num_rows: int) -> None:
        """Build a widget of *num_rows* rows."""
        super().__init__()
        self.num_rows = num_rows

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the number of rows given to the constructor."""
        return self.num_rows

    def render(self, size: tuple[int], focus: bool = False) -> urwid.TextCanvas:
        """Render the rows; a box size fails to unpack."""
        (maxcol,) = size
        return urwid.TextCanvas([str(i).encode().ljust(maxcol) for i in range(self.num_rows)], maxcol=maxcol)


def make_table(num_rows: int) -> urwid.Table:
    """Return a one-column table of *num_rows* rows ``r0``, ``r1``, ... with no header.

    A table supports both FLOW and BOX sizing, and scrolls at a box size.
    """
    return urwid.Table([urwid.TableColumn()], [[f"r{i}"] for i in range(num_rows)], header=False)


class FillerTest(unittest.TestCase):
    def test_layout_attributes_invalidate(self) -> None:
        """Setting a layout attribute of a rendered ``Filler`` redraws it."""

        def make_text(valign: str) -> typing.Callable[..., urwid.Filler]:
            return lambda **kwargs: urwid.Filler(urwid.Text("ab"), valign=valign, **kwargs)

        def make_relative(**kwargs: typing.Any) -> urwid.Filler:
            return urwid.Filler(urwid.SolidFill("x"), height=("relative", 20), **kwargs)

        for name, make, value in (
            ("top", make_text("top"), 2),
            ("bottom", make_text("bottom"), 2),
            ("min_height", make_relative, 4),
            (
                "shrink_to_fit",
                lambda **kwargs: urwid.Filler(urwid.LineBox(make_table(12)), valign="top", **kwargs),
                True,
            ),
        ):
            with self.subTest(name):
                assert_attribute_redraws(self, make, (2, 10), name, value)

    def ftest(
        self,
        desc: str,
        valign,
        height,
        maxrow: int,
        top: int,
        bottom: int,
        min_height: int | None = None,
    ) -> None:
        with self.subTest(desc):
            f = urwid.Filler(urwid.SolidFill(), valign, height, min_height)
            t, b = f.filler_values((20, maxrow), False)
            self.assertEqual(
                (t, b),
                (top, bottom),
                f"{desc} expected {top, bottom} but got {t, b}",
            )

    def fetest(self, desc: str, valign, height) -> None:
        with self.subTest(desc):
            self.assertRaises(urwid.FillerError, urwid.Filler, urwid.SolidFill(), valign, height)

    def test_create(self):
        self.fetest("invalid pad", 6, 5)
        self.fetest("invalid pad type", ("bad", 2), 5)
        self.fetest("invalid width", "middle", "42")
        self.fetest("invalid width type", "middle", ("gouranga", 4))
        self.fetest("invalid combination", ("relative", 20), ("fixed bottom", 4))
        self.fetest("invalid combination 2", ("relative", 20), ("fixed top", 4))

    def test_values(self):
        self.ftest("top align 5 7", "top", 5, 7, 0, 2)
        self.ftest("top align 7 7", "top", 7, 7, 0, 0)
        self.ftest("top align 9 7", "top", 9, 7, 0, 0)
        self.ftest("bottom align 5 7", "bottom", 5, 7, 2, 0)
        self.ftest("middle align 5 7", "middle", 5, 7, 1, 1)
        self.ftest("fixed top", ("fixed top", 3), 5, 10, 3, 2)
        self.ftest("fixed top reduce", ("fixed top", 3), 8, 10, 2, 0)
        self.ftest("fixed top shrink", ("fixed top", 3), 18, 10, 0, 0)
        self.ftest(
            "fixed top, bottom",
            ("fixed top", 3),
            ("fixed bottom", 4),
            17,
            3,
            4,
        )
        self.ftest(
            "fixed top, bottom, min_width",
            ("fixed top", 3),
            ("fixed bottom", 4),
            10,
            3,
            2,
            5,
        )
        self.ftest(
            "fixed top, bottom, min_width 2",
            ("fixed top", 3),
            ("fixed bottom", 4),
            10,
            2,
            0,
            8,
        )
        self.ftest("fixed bottom", ("fixed bottom", 3), 5, 10, 2, 3)
        self.ftest("fixed bottom reduce", ("fixed bottom", 3), 8, 10, 0, 2)
        self.ftest("fixed bottom shrink", ("fixed bottom", 3), 18, 10, 0, 0)
        self.ftest(
            "fixed bottom, top",
            ("fixed bottom", 3),
            ("fixed top", 4),
            17,
            4,
            3,
        )
        self.ftest(
            "fixed bottom, top, min_height",
            ("fixed bottom", 3),
            ("fixed top", 4),
            10,
            2,
            3,
            5,
        )
        self.ftest(
            "fixed bottom, top, min_height 2",
            ("fixed bottom", 3),
            ("fixed top", 4),
            10,
            0,
            2,
            8,
        )
        self.ftest("relative 30", ("relative", 30), 5, 10, 1, 4)
        self.ftest("relative 50", ("relative", 50), 5, 10, 2, 3)
        self.ftest("relative 130 edge", ("relative", 130), 5, 10, 5, 0)
        self.ftest("relative -10 edge", ("relative", -10), 4, 10, 0, 6)
        self.ftest("middle relative 70", "middle", ("relative", 70), 10, 1, 2)
        self.ftest(
            "middle relative 70 grow 8",
            "middle",
            ("relative", 70),
            10,
            1,
            1,
            8,
        )

    def test_repr(self):
        self.assertEqual(
            "<Filler box/flow widget <Text fixed/flow widget 'hai'>>",
            repr(urwid.Filler(urwid.Text("hai"))),
        )
        self.assertEqual(
            "<Filler box/flow widget <Text fixed/flow widget 'hai'> shrink_to_fit=True>",
            repr(urwid.Filler(urwid.Text("hai"), shrink_to_fit=True)),
        )

    def test_sizing(self):
        with self.subTest("Flow supported for PACK height (flow widget)"):
            widget = urwid.Filler(urwid.Text("Some text"))
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())

            cols, rows = 10, 1
            self.assertEqual((cols, rows), widget.pack((cols,)))  # top and bottom are 0
            self.assertEqual((cols, rows), widget.pack((cols, rows)))

            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            canvas = widget.render((cols, rows))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("Flow supported for GIVEN height (box widget)"):
            widget = urwid.Filler(urwid.SolidFill("#"), height=3)
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())

            cols, rows = 5, 3
            self.assertEqual((cols, rows), widget.pack((cols,)))  # top and bottom are 0
            self.assertEqual((cols, rows), widget.pack((cols, rows)))

            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            canvas = widget.render((cols, rows))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("Flow is not supported for RELATIVE scenarios"):
            widget = urwid.Filler(urwid.SolidFill(""), height=(urwid.RELATIVE, 10))
            cols = 10
            with self.assertRaises(urwid.widget.WidgetError) as ctx:
                widget.pack((cols,))

            self.assertEqual(
                f"Cannot pack (maxcol,) size, this is not a flow widget: {widget!r}",
                str(ctx.exception),
            )

            with self.assertRaises(urwid.widget.WidgetError) as ctx:
                widget.render((cols,))

            self.assertEqual(
                f"Cannot pack (maxcol,) size, this is not a flow widget: {widget!r}",
                str(ctx.exception),
            )

    def test_sizing_pack_height_requires_flow_body(self):
        """A PACK height is only meaningful for a FLOW body: warn instead of failing obscurely later.

        With a BOX-only body and the default PACK height the filler declares BOX and FLOW support,
        yet every render raises ``AttributeError`` from the missing ``rows`` method,
        so the mismatch has to be announced while the sizing is calculated.
        """
        widget = urwid.Filler(urwid.SolidFill("#"))

        with self.assertWarns(urwid.widget.FillerWarning) as ctx:
            sizing = widget.sizing()

        self.assertEqual(
            f"WHSettings.PACK height expects a FLOW widget to be used, but received {widget.original_widget!r}",
            str(ctx.warning),
        )
        # The declared sizing is deliberately left untouched: containers branch on it while laying out.
        self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), sizing)

    def test_sizing_pack_height_flow_body_does_not_warn(self):
        """A FLOW body with a PACK height is the supported combination and must stay silent."""
        widget = urwid.Filler(urwid.Text("Some text"))

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())

    def test_render_focused_not_fit(self):
        """Test that a focused widget will be shown and top trimmed if not enough height."""
        widget = urwid.Filler(
            urwid.Pile(
                (
                    urwid.Text("First"),
                    urwid.Text("Second"),
                    urwid.Text("Third"),
                    urwid.Button("Selectable"),
                    urwid.Text("Last"),
                ),
            )
        )

        canvas = widget.render((14, 3), focus=True)
        self.assertEqual(
            [
                b"Second        ",
                b"Third         ",
                b"< Selectable >",
            ],
            canvas.text,
        )

    def test_valign_top_around_text(self) -> None:
        """Body filler used by dialog windows."""
        filler = urwid.Filler(urwid.Text("body"), valign=urwid.TOP)

        self.assertEqual((4, 3), filler.pack((4, 3)))
        self.assertEqual([b"body", b"    ", b"    "], filler.render((4, 3)).text)

    def test_shrink_to_fit(self) -> None:
        """With shrink_to_fit, a PACK body taller than the rows available is rendered as a box at those rows.

        The body keeps its border and scrolls.
        A body that fits is rendered at its flow size, and the flag off clips the body as before.
        """
        body = urwid.LineBox(make_table(6))
        flow_text = urwid.testing.render_text(body, (6,), focus=True)
        self.assertEqual(8, len(flow_text))
        filler = urwid.Filler(body, valign="top", shrink_to_fit=True)
        self.assertEqual(
            ["┌────┐", "│r0  │", "│r1  │", "└────┘"],
            urwid.testing.render_text(filler, (6, 4), focus=True),
        )
        self.assertEqual([], urwid.testing.press(filler, (6, 4), *["down"] * 5))
        self.assertEqual(
            ["┌────┐", "│r4  │", "│r5  │", "└────┘"],
            urwid.testing.render_text(filler, (6, 4), focus=True),
        )
        self.assertEqual([*flow_text, " " * 6], urwid.testing.render_text(filler, (6, 9), focus=True))
        urwid.testing.check_sizing(filler, cols=6, rows=4)

        clipped = urwid.Filler(urwid.LineBox(make_table(6)), valign="top")
        self.assertEqual(flow_text[:4], urwid.testing.render_text(clipped, (6, 4), focus=True))

    def test_shrink_to_fit_with_margins(self) -> None:
        """The rows between the top and bottom margins are the box a body taller than them is rendered at."""
        filler = urwid.Filler(urwid.LineBox(make_table(6)), top=1, bottom=1, shrink_to_fit=True)
        self.assertEqual(
            ["      ", "┌────┐", "│r0  │", "│r1  │", "└────┘", "      "],
            urwid.testing.render_text(filler, (6, 6), focus=True),
        )

    def test_shrink_to_fit_focus_dependent_height(self) -> None:
        """A body taller than the rows available only in focus is rendered as a box in either focus.

        Mouse events reach it at the size it is rendered at in focus.
        """
        body = FocusHeightWidget()
        filler = urwid.Filler(body, valign="top", shrink_to_fit=True)
        size = (4, 3)
        for focus, lines in ((False, ["xxxx", "xxxx", "    "]), (True, ["xxxx", "xxxx", "xxxx"])):
            with self.subTest(focus=focus):
                self.assertEqual(lines, urwid.testing.render_text(filler, size, focus=focus))
        self.assertTrue(filler.mouse_event(size, "mouse press", 1, 0, 0, True))
        self.assertEqual([("mouse_event", (4, 3))], body.sizes)

    def test_shrink_to_fit_input_sizes(self) -> None:
        """Keys, mouse events and the cursor reach a body taller than the rows available at the box size.

        With the flag off they reach it at the flow size.
        """
        for shrink_to_fit, body_size in ((True, (10, 2)), (False, (10,))):
            with self.subTest(shrink_to_fit=shrink_to_fit):
                body = CursorWidget([urwid.BOX, urwid.FLOW], num_rows=5)
                widget = urwid.Filler(body, valign="top", top=1, shrink_to_fit=shrink_to_fit)
                size = (10, 3)
                widget.keypress(size, "enter")
                widget.get_cursor_coords(size)
                widget.get_pref_col(size)
                widget.move_cursor_to_coords(size, 0, 1)
                widget.mouse_event(size, "mouse press", 1, 0, 1, True)
                self.assertEqual(
                    [
                        (method, body_size)
                        for method in (
                            "keypress",
                            "get_cursor_coords",
                            "get_pref_col",
                            "move_cursor_to_coords",
                            "mouse_event",
                        )
                    ],
                    body.sizes,
                )

    def test_shrink_to_fit_without_box_support(self) -> None:
        """A body without BOX support is clipped with the flag set, as without it."""
        for shrink_to_fit in (False, True):
            with self.subTest(shrink_to_fit=shrink_to_fit):
                widget = urwid.Filler(TrimWidget(5, cursor=(0, 4)), shrink_to_fit=shrink_to_fit)
                canvas = widget.render((10, 3), focus=True)
                self.assertEqual(3, canvas.rows())
                self.assertEqual((0, 2), canvas.cursor)

    def test_box_claim_without_box_render_is_unaffected_by_default(self) -> None:
        """A body that claims BOX but renders only at a flow size is rendered at its flow size, and clipped."""
        body = FlowOnlyRenderWidget(5)
        self.assertEqual(["0", "1", "2"], urwid.testing.render_text(urwid.Filler(body), (1, 3)))

    def test_render_trim_no_cursor(self) -> None:
        """When the body has no cursor, an oversized canvas is trimmed straight to maxrow."""
        widget = urwid.Filler(TrimWidget(5))

        canvas = widget.render((10, 3), focus=False)

        self.assertEqual(3, canvas.rows())
        self.assertIsNone(canvas.cursor)

    def test_render_trim_cursor_within_maxrow(self) -> None:
        """A cursor above maxrow does not trigger the cursor-driven trim, but the oversized canvas is still cut."""
        widget = urwid.Filler(TrimWidget(5, cursor=(0, 1)))

        canvas = widget.render((10, 3), focus=True)

        self.assertEqual(3, canvas.rows())
        self.assertEqual((0, 1), canvas.cursor)

    def test_render_trim_cursor_beyond_maxrow(self) -> None:
        """A cursor beyond maxrow triggers the cursor-driven top trim, keeping the cursor row visible."""
        widget = urwid.Filler(TrimWidget(5, cursor=(0, 4)))

        canvas = widget.render((10, 3), focus=True)

        self.assertEqual(3, canvas.rows())
        self.assertEqual((0, 2), canvas.cursor)

    def test_keypress_pack_height(self) -> None:
        body = CursorWidget([urwid.FLOW], num_rows=1)
        widget = urwid.Filler(body)

        self.assertIsNone(widget.keypress((10,), "enter"))

    def test_keypress_given_height(self) -> None:
        body = CursorWidget([urwid.BOX])
        widget = urwid.Filler(body, height=3)

        self.assertIsNone(widget.keypress((10, 5), "enter"))

    def test_get_cursor_coords_no_cursor_api(self) -> None:
        widget = urwid.Filler(PlainBoxWidget(), height=3)

        self.assertIsNone(widget.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_falsy_coords(self) -> None:
        body = CursorWidget([urwid.BOX], cursor=None)
        widget = urwid.Filler(body, height=3)

        self.assertIsNone(widget.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_pack_height(self) -> None:
        body = CursorWidget([urwid.FLOW], num_rows=1, cursor=(2, 0))
        widget = urwid.Filler(body)

        self.assertEqual((2, 1), widget.get_cursor_coords((10, 3)))

    def test_get_cursor_coords_given_height(self) -> None:
        body = CursorWidget([urwid.BOX], cursor=(2, 1))
        widget = urwid.Filler(body, height=3)

        self.assertEqual((2, 2), widget.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_clamps_to_maxrow(self) -> None:
        """The body may report a cursor row beyond maxrow; Filler clamps it to the last visible row."""
        body = CursorWidget([urwid.BOX], cursor=(0, 10))
        widget = urwid.Filler(body, height=3)

        self.assertEqual((0, 5), widget.get_cursor_coords((10, 5)))

    def test_get_pref_col_no_cursor_api(self) -> None:
        widget = urwid.Filler(PlainBoxWidget(), height=3)

        self.assertIsNone(widget.get_pref_col((10, 5)))

    def test_get_pref_col_pack_height(self) -> None:
        body = CursorWidget([urwid.FLOW], num_rows=1, cursor=(2, 0))
        widget = urwid.Filler(body)

        self.assertEqual(2, widget.get_pref_col((10, 3)))

    def test_get_pref_col_given_height(self) -> None:
        body = CursorWidget([urwid.BOX], cursor=(2, 0))
        widget = urwid.Filler(body, height=3)

        self.assertEqual(2, widget.get_pref_col((10, 5)))

    def test_move_cursor_to_coords_no_cursor_api(self) -> None:
        widget = urwid.Filler(PlainBoxWidget(), height=3)

        self.assertTrue(widget.move_cursor_to_coords((10, 5), 0, 0))

    def test_move_cursor_to_coords_out_of_range_row(self) -> None:
        body = CursorWidget([urwid.BOX])
        widget = urwid.Filler(body, height=3)

        self.assertFalse(widget.move_cursor_to_coords((10, 5), 0, 0))

    def test_move_cursor_to_coords_bottom_row_of_narrow_box(self) -> None:
        """The last row is measured from the height of the box, not from its width."""
        widget = urwid.Filler(urwid.Edit("", "abc"), valign=urwid.BOTTOM)

        self.assertTrue(widget.move_cursor_to_coords((5, 10), 2, 9))
        self.assertEqual(2, widget.original_widget.edit_pos)
        self.assertFalse(widget.move_cursor_to_coords((10, 5), 2, 3))

    def test_move_cursor_to_coords_pack_height(self) -> None:
        body = CursorWidget([urwid.FLOW], num_rows=1)
        widget = urwid.Filler(body)

        self.assertTrue(widget.move_cursor_to_coords((10, 3), 2, 1))

    def test_move_cursor_to_coords_given_height(self) -> None:
        body = CursorWidget([urwid.BOX], move_result=False)
        widget = urwid.Filler(body, height=3)

        self.assertFalse(widget.move_cursor_to_coords((10, 5), 2, 2))

    def test_mouse_event_non_widget_body(self) -> None:
        with self.assertWarns(DeprecationWarning):
            widget = urwid.Filler(NonWidgetBox(), height=3)  # type: ignore[arg-type]

        self.assertFalse(widget.mouse_event((10, 5), "mouse press", 1, 0, 0, False))

    def test_mouse_event_out_of_range_row(self) -> None:
        body = CursorWidget([urwid.BOX])
        widget = urwid.Filler(body, height=3)

        self.assertFalse(widget.mouse_event((10, 5), "mouse press", 1, 0, 0, True))

    def test_mouse_event_pack_height(self) -> None:
        body = CursorWidget([urwid.FLOW], num_rows=1)
        widget = urwid.Filler(body)

        self.assertTrue(widget.mouse_event((10, 3), "mouse press", 1, 2, 1, True))

    def test_mouse_event_given_height(self) -> None:
        body = CursorWidget([urwid.BOX], mouse_result=False)
        widget = urwid.Filler(body, height=3)

        self.assertFalse(widget.mouse_event((10, 5), "mouse press", 1, 2, 2, True))

    def test_calculate_top_bottom_filler_relative_valign_requires_amount(self) -> None:
        with self.assertRaises(TypeError):
            urwid.widget.calculate_top_bottom_filler(10, urwid.RELATIVE, None, urwid.GIVEN, 5, None, 0, 0)

    def test_squish(self):
        urwid.testing.check_box_sizing(urwid.Filler(urwid.Text("hello")))
