from __future__ import annotations

import unittest
from unittest import mock

import urwid


class GridFlowTest(unittest.TestCase):
    def test_fixed(self):
        grid = urwid.GridFlow(
            (urwid.Button(tag, align=urwid.CENTER) for tag in ("OK", "Cancel", "Help")),
            cell_width=10,
            h_sep=1,
            v_sep=1,
            align=urwid.CENTER,
        )
        self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), grid.sizing())

        cols, rows = 32, 1
        self.assertEqual((cols, rows), grid.pack(()))
        canvas = grid.render(())
        self.assertEqual(cols, canvas.cols())
        self.assertEqual(rows, canvas.rows())
        self.assertEqual([b"<   OK   > < Cancel > <  Help  >"], canvas.text)

    def test_default_focus(self):
        with self.subTest("Simple"):
            grid = urwid.GridFlow(
                (urwid.Button("btn"), urwid.Button("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
            )
            self.assertTrue(grid.selectable())
            self.assertEqual(0, grid.focus_position)

        with self.subTest("Simple not selectable"):
            grid = urwid.GridFlow(
                (urwid.Text("btn"), urwid.Text("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
            )
            self.assertFalse(grid.selectable())
            self.assertEqual(0, grid.focus_position)

        with self.subTest("Explicit index"):
            grid = urwid.GridFlow(
                (urwid.Button("btn"), urwid.Button("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
                focus=1,
            )
            self.assertEqual(1, grid.focus_position)

        with self.subTest("Explicit widget"):
            btn2 = urwid.Button("btn 2")
            grid = urwid.GridFlow(
                (urwid.Button("btn"), btn2),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
                focus=btn2,
            )
            self.assertEqual(1, grid.focus_position)

        with self.subTest("Selectable not first"):
            grid = urwid.GridFlow(
                (urwid.Text("text"), urwid.Button("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
            )
            self.assertEqual(1, grid.focus_position)

    def test_cell_width(self):
        gf = urwid.GridFlow([], 5, 0, 0, "left")
        self.assertEqual(gf.cell_width, 5)

    def test_not_fit(self):
        """Test scenario with maxcol < cell_width (special case, warning will be produced)."""
        widget = urwid.GridFlow(
            [urwid.Button("first"), urwid.Button("second")],
            5,
            0,
            0,
            "left",
        )
        size = (3,)
        with self.assertWarns(urwid.widget.GridFlowWarning):
            canvas = widget.render(size)

        self.assertEqual(
            ("< f", "  i", "  r", "  s", "  t", "< s", "  e", "  c", "  o", "  n", "  d"),
            canvas.decoded_text,
        )

    def test_multiline(self):
        """Test widgets fit only with multiple lines"""
        widget = urwid.GridFlow(
            [urwid.Button("first"), urwid.Button("second")],
            10,
            0,
            0,
            "left",
        )
        size = (10,)
        canvas = widget.render(size)
        self.assertEqual(
            ("< first  >", "< second >"),
            canvas.decoded_text,
        )

    def test_multiline_2(self):
        """Test widgets fit only with multiple lines"""
        widget = urwid.GridFlow(
            [urwid.Button("first"), urwid.Button("second"), urwid.Button("third"), urwid.Button("forth")],
            10,
            0,
            0,
            "left",
        )
        size = (20,)
        canvas = widget.render(size)
        self.assertEqual(
            (
                "< first  >< second >",
                "< third  >< forth  >",
            ),
            canvas.decoded_text,
        )

    def test_basics(self):
        repr(urwid.GridFlow([], 5, 0, 0, "left"))  # should not fail

    def test_v_sep(self):
        gf = urwid.GridFlow([urwid.Text("test")], 10, 3, 1, "center")
        self.assertEqual(gf.rows((40,), False), 1)

    def test_keypress_v_sep_0(self):
        """
        Ensure proper keypress handling when v_sep is 0.
        https://github.com/urwid/urwid/issues/387
        """
        call_back = mock.Mock()
        button = urwid.Button("test", call_back)
        gf = urwid.GridFlow([button], 10, 3, v_sep=0, align="center")
        self.assertEqual(gf.keypress((20,), "enter"), None)
        call_back.assert_called_with(button)

    def test_length(self):
        grid = urwid.GridFlow((urwid.Text(c) for c in "ABC"), 1, 0, 0, "left")
        self.assertEqual(3, len(grid))
        self.assertEqual(3, len(grid.contents))

    def test_common(self):
        gf = urwid.GridFlow([], 5, 1, 0, "left")

        with self.subTest("Focus"):
            self.assertEqual(gf.focus, None)
            self.assertEqual(gf.contents, [])
            self.assertRaises(IndexError, lambda: getattr(gf, "focus_position"))
            self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", None))
            self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", 0))

        with self.subTest("Contents options"):
            self.assertEqual(gf.options(), ("given", 5))
            self.assertEqual(gf.options(width_amount=9), ("given", 9))
            self.assertRaises(urwid.GridFlowError, lambda: gf.options("pack", None))

    def test_focus_position(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        gf = urwid.GridFlow([t1, t2], 5, 1, 0, "left")
        self.assertEqual(gf.focus, t1)
        self.assertEqual(gf.focus_position, 0)
        self.assertEqual(gf.contents, [(t1, ("given", 5)), (t2, ("given", 5))])
        gf.focus_position = 1
        self.assertEqual(gf.focus, t2)
        self.assertEqual(gf.focus_position, 1)
        gf.contents.insert(0, (t2, ("given", 5)))
        self.assertEqual(gf.focus_position, 2)
        self.assertRaises(urwid.GridFlowError, lambda: gf.contents.append(()))
        self.assertRaises(urwid.GridFlowError, lambda: gf.contents.insert(1, (t1, ("pack", None))))
        gf.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", -1))
        self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", 3))

    def test_deprecated(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        gf = urwid.GridFlow([t1, t2], 5, 1, 0, "left")
        # old methods:
        gf.set_focus(0)
        self.assertRaises(IndexError, lambda: gf.set_focus(-1))
        self.assertRaises(IndexError, lambda: gf.set_focus(3))
        gf.set_focus(t1)
        self.assertEqual(gf.focus_position, 0)
        self.assertRaises(ValueError, lambda: gf.set_focus("nonexistant"))

    def test_empty(self):
        """Test behaviour of empty widget."""
        grid = urwid.GridFlow(
            (),
            cell_width=10,
            h_sep=1,
            v_sep=1,
            align=urwid.CENTER,
        )
        self.assertEqual(frozenset((urwid.FLOW,)), grid.sizing(), "Empty grid can not be handled as FIXED")
        rows = 1
        with self.subTest("Flow"):
            maxcol = 1
            self.assertEqual((maxcol, rows), grid.pack((maxcol,)))
            rendered = grid.render((maxcol,))
            self.assertEqual(maxcol, rendered.cols())
            self.assertEqual(rows, rendered.rows())

        with self.subTest("Fixed"):
            maxcol = 0
            self.assertEqual((maxcol, rows), grid.pack(()))
            with self.assertRaises(ValueError):
                grid.render(())
