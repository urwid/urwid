from __future__ import annotations

import unittest
import warnings

import urwid


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
