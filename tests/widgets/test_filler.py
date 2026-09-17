from __future__ import annotations

import unittest
import warnings

import urwid


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
        return None

    def get_cursor_coords(self, size: tuple[int, int] | tuple[int]) -> tuple[int, int] | None:
        return self.cursor_pos

    def get_pref_col(self, size: tuple[int, int] | tuple[int]) -> int:
        return self.cursor_pos[0] if self.cursor_pos else 0

    def move_cursor_to_coords(self, size: tuple[int, int] | tuple[int], col: int, row: int) -> bool:
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
        return self.mouse_result


class PlainBoxWidget:
    """A box widget that implements only the bare minimum, lacking cursor-related methods entirely.

    Unlike a :class:`urwid.Widget` subclass (which inherits default ``mouse_event``/``keypress`` implementations),
    this class has no ``get_cursor_coords``, ``get_pref_col``, ``move_cursor_to_coords``, or ``mouse_event``
    attribute at all, so ``hasattr`` checks on it are ``False``.
    """

    def sizing(self) -> frozenset[urwid.Sizing]:
        return frozenset((urwid.BOX,))

    def selectable(self) -> bool:
        return False

    def pack(self, size: tuple[int, int], focus: bool = False) -> tuple[int, int]:
        return size

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


class FillerTest(unittest.TestCase):
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
            f = urwid.Filler(None, valign, height, min_height)
            t, b = f.filler_values((20, maxrow), False)
            self.assertEqual(
                (t, b),
                (top, bottom),
                f"{desc} expected {top, bottom} but got {t, b}",
            )

    def fetest(self, desc: str, valign, height) -> None:
        with self.subTest(desc):
            self.assertRaises(urwid.FillerError, urwid.Filler, None, valign, height)

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

    def test_move_cursor_to_coords_pack_height(self) -> None:
        body = CursorWidget([urwid.FLOW], num_rows=1)
        widget = urwid.Filler(body)

        self.assertTrue(widget.move_cursor_to_coords((10, 3), 2, 1))

    def test_move_cursor_to_coords_given_height(self) -> None:
        body = CursorWidget([urwid.BOX], move_result=False)
        widget = urwid.Filler(body, height=3)

        self.assertFalse(widget.move_cursor_to_coords((10, 5), 2, 2))

    def test_mouse_event_no_cursor_api(self) -> None:
        widget = urwid.Filler(PlainBoxWidget(), height=3)

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
