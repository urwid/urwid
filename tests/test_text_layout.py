from __future__ import annotations

import sys
import threading
import typing
import unittest
import unittest.mock

import wcwidth

import urwid
from urwid import canvas, text_layout
from urwid.util import get_encoding, set_temporary_encoding

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Literal


class CalcBreaksTest(unittest.TestCase):
    def cbtest(self, width, exp, mode, text):
        result = text_layout.default_layout.calculate_text_segments(text, width, mode)
        self.assertEqual(len(exp), len(result), f"Expected: {exp!r}, got {result!r}")
        for l, e in zip(result, exp):
            end = l[-1][-1]
            self.assertEqual(e, end, f"Expected: {exp!r}, got {result!r}")

    def validate(self, mode, text, do):
        for width, exp in do:
            self.cbtest(width, exp, mode, text)

    def test_calc_breaks_char(self):
        self.validate(
            mode="any",
            text=b"abfghsdjf askhtrvs\naltjhgsdf ljahtshgf",
            do=[
                (100, [18, 38]),
                (6, [6, 12, 18, 25, 31, 37, 38]),
                (10, [10, 18, 29, 38]),
            ],
        )

    def test_calc_reaks_db_char(self):
        with urwid.util.set_temporary_encoding("euc-jp"):
            self.validate(
                mode="any",
                text=b"abfgh\xa1\xa1j\xa1\xa1xskhtrvs\naltjhgsdf\xa1\xa1jahtshgf",
                do=[
                    (10, [10, 18, 28, 38]),
                    (6, [5, 11, 17, 18, 25, 31, 37, 38]),
                    (100, [18, 38]),
                ],
            )

    def test_calc_breaks_word(self):
        self.validate(
            mode="space",
            text=b"hello world\nout there. blah",
            do=[
                (10, [5, 11, 22, 27]),
                (5, [5, 11, 17, 22, 27]),
                (100, [11, 27]),
            ],
        )

    def test_calc_breaks_word_2(self):
        self.validate(
            mode="space",
            text=b"A simple set of words, really....",
            do=[
                (10, [8, 15, 22, 33]),
                (17, [15, 33]),
                (13, [12, 22, 33]),
            ],
        )

    def test_calc_breaks_db_word(self):
        with urwid.util.set_temporary_encoding("euc-jp"):
            self.validate(
                mode="space",
                text=b"hel\xa1\xa1 world\nout-\xa1\xa1tre blah",
                # tests
                do=[
                    (10, [5, 11, 21, 26]),
                    (5, [5, 11, 16, 21, 26]),
                    (100, [11, 26]),
                ],
            )

    def test_calc_breaks_utf8(self):
        with urwid.util.set_temporary_encoding("utf-8"):
            self.validate(
                mode="space",
                # As text: "替洼渎溏潺"
                text=b"\xe6\x9b\xbf\xe6\xb4\xbc\xe6\xb8\x8e\xe6\xba\x8f\xe6\xbd\xba",
                do=[
                    (4, [6, 12, 15]),
                    (10, [15]),
                    (5, [6, 12, 15]),
                ],
            )


class CalcBreaksCantDisplayTest(unittest.TestCase):
    def test(self):
        with set_temporary_encoding("euc-jp"):
            self.assertRaises(
                text_layout.CanNotDisplayText,
                text_layout.default_layout.calculate_text_segments,
                b"\xa1\xa1",
                1,
                "space",
            )
        with set_temporary_encoding("utf-8"):
            self.assertRaises(
                text_layout.CanNotDisplayText,
                text_layout.default_layout.calculate_text_segments,
                "颖",
                1,
                "space",
            )


class SubsegTest(unittest.TestCase):
    def setUp(self):
        self.old_encoding = get_encoding()
        urwid.set_encoding("euc-jp")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def st(self, seg, text: bytes, start: int, end: int, exp):
        s = urwid.LayoutSegment(seg)
        result = s.subseg(text, start, end)
        self.assertEqual(exp, result, f"Expected {exp!r}, got {result!r}")

    def test1_padding(self):
        self.st((10, None), b"", 0, 8, [(8, None)])
        self.st((10, None), b"", 2, 10, [(8, None)])
        self.st((10, 0), b"", 3, 7, [(4, 0)])
        self.st((10, 0), b"", 0, 20, [(10, 0)])

    def test2_text(self):
        self.st((10, 0, b"1234567890"), b"", 0, 8, [(8, 0, b"12345678")])
        self.st((10, 0, b"1234567890"), b"", 2, 10, [(8, 0, b"34567890")])
        self.st((10, 0, b"12\xa1\xa156\xa1\xa190"), b"", 2, 8, [(6, 0, b"\xa1\xa156\xa1\xa1")])
        self.st((10, 0, b"12\xa1\xa156\xa1\xa190"), b"", 3, 8, [(5, 0, b" 56\xa1\xa1")])
        self.st((10, 0, b"12\xa1\xa156\xa1\xa190"), b"", 2, 7, [(5, 0, b"\xa1\xa156 ")])
        self.st((10, 0, b"12\xa1\xa156\xa1\xa190"), b"", 3, 7, [(4, 0, b" 56 ")])
        self.st((10, 0, b"12\xa1\xa156\xa1\xa190"), b"", 0, 20, [(10, 0, b"12\xa1\xa156\xa1\xa190")])

    def test3_range(self):
        t = b"1234567890"
        self.st((10, 0, 10), t, 0, 8, [(8, 0, 8)])
        self.st((10, 0, 10), t, 2, 10, [(8, 2, 10)])
        self.st((6, 2, 8), t, 1, 6, [(5, 3, 8)])
        self.st((6, 2, 8), t, 0, 5, [(5, 2, 7)])
        self.st((6, 2, 8), t, 1, 5, [(4, 3, 7)])
        t = b"12\xa1\xa156\xa1\xa190"
        self.st((10, 0, 10), t, 0, 8, [(8, 0, 8)])
        self.st((10, 0, 10), t, 2, 10, [(8, 2, 10)])
        self.st((6, 2, 8), t, 1, 6, [(1, 2), (4, 4, 8)])
        self.st((6, 2, 8), t, 0, 5, [(4, 2, 6), (1, 6)])
        self.st((6, 2, 8), t, 1, 5, [(1, 2), (2, 4, 6), (1, 6)])

    def test4_range_inside_a_wide_character(self):
        """A window that lands inside a wide character is padding pointing at the start of that character."""
        t = b"12\xa1\xa156\xa1\xa190"
        self.st((10, 0, 10), t, 2, 3, [(1, 2)])
        self.st((10, 0, 10), t, 3, 4, [(1, 2)])
        self.st((10, 0, 10), t, 7, 8, [(1, 6)])
        self.st((6, 2, 8), t, 1, 2, [(1, 2)])


class NarrowWideCharacterRenderTest(unittest.TestCase):
    """Rendering wide characters into an area too narrow to hold them."""

    CJK = "你好世界"

    def render(self, widget, size, focus: bool = False) -> list[str]:
        return [line.decode("utf-8") for line in widget.render(size, focus).text]

    def test_clipped_on_both_edges(self):
        with set_temporary_encoding("utf-8"):
            self.assertEqual([" "], self.render(urwid.Text(self.CJK, wrap="clip"), (1,)))
            self.assertEqual(["你 "], self.render(urwid.Text(self.CJK, wrap="clip"), (3,)))
            self.assertEqual(["  "], self.render(urwid.Text(self.CJK, align="center", wrap="clip"), (2,)))
            self.assertEqual([" "], self.render(urwid.Text(self.CJK, align="right", wrap="clip"), (1,)))

    def test_inside_a_line_box(self):
        with set_temporary_encoding("utf-8"):
            self.assertEqual(
                ["┌─┐", "│ │", "└─┘"],
                self.render(urwid.LineBox(urwid.Text(self.CJK, wrap="clip")), (3,)),
            )

    def test_shifted_left_by_padding(self):
        with set_temporary_encoding("utf-8"):
            self.assertEqual(
                [" "],
                self.render(urwid.Padding(urwid.Text(self.CJK, wrap="clip"), left=-1), (1,)),
            )

    def test_every_narrow_width_renders(self):
        with set_temporary_encoding("utf-8"):
            for align in (urwid.Align.LEFT, urwid.Align.CENTER, urwid.Align.RIGHT):
                for width in range(1, 10):
                    with self.subTest(align=align, width=width):
                        canvas = urwid.Text(self.CJK, align=align, wrap=urwid.WrapMode.CLIP).render((width,))
                        self.assertEqual(width, canvas.cols())


class CalcTranslateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def check(self, text, mode, width, result_left, result_center, result_right) -> None:
        with self.subTest("left"):
            result = urwid.default_layout.layout(text, width, "left", mode)
            self.assertEqual(
                result_left,
                result,
                f"For {text=} {width=} {mode=} got {result!r} instead of {result_left!r}",
            )

        with self.subTest("center"):
            result = urwid.default_layout.layout(text, width, "center", mode)
            self.assertEqual(
                result_center,
                result,
                f"For {text=} {width=} {mode=} got {result!r} instead of {result_center!r}",
            )

        with self.subTest("right"):
            result = urwid.default_layout.layout(text, width, "right", mode)
            self.assertEqual(
                result_right,
                result,
                f"For {text=} {width=} {mode=} got {result!r} instead of {result_right!r}",
            )

    def test_calc_translate_char(self):
        self.check(
            text="It's out of control!\nYou've got to",
            mode="any",
            width=15,
            result_left=[[(15, 0, 15)], [(5, 15, 20), (0, 20)], [(13, 21, 34), (0, 34)]],
            result_center=[[(15, 0, 15)], [(5, None), (5, 15, 20), (0, 20)], [(1, None), (13, 21, 34), (0, 34)]],
            result_right=[[(15, 0, 15)], [(10, None), (5, 15, 20), (0, 20)], [(2, None), (13, 21, 34), (0, 34)]],
        )

    def test_calc_translate_word(self):
        self.check(
            text="It's out of control!\nYou've got to",
            mode="space",
            width=14,
            result_left=[
                [(11, 0, 11), (0, 11)],
                [(8, 12, 20), (0, 20)],
                [(13, 21, 34), (0, 34)],
            ],
            result_center=[
                [(2, None), (11, 0, 11), (0, 11)],
                [(3, None), (8, 12, 20), (0, 20)],
                [(1, None), (13, 21, 34), (0, 34)],
            ],
            result_right=[
                [(3, None), (11, 0, 11), (0, 11)],
                [(6, None), (8, 12, 20), (0, 20)],
                [(1, None), (13, 21, 34), (0, 34)],
            ],
        )

    def test_calc_translate(self):
        self.check(
            text="It's out of control!\nYou've got to ",
            mode="space",
            width=14,
            result_left=[
                [(11, 0, 11), (0, 11)],
                [(8, 12, 20), (0, 20)],
                [(14, 21, 35), (0, 35)],
            ],
            result_center=[
                [(2, None), (11, 0, 11), (0, 11)],
                [(3, None), (8, 12, 20), (0, 20)],
                [(14, 21, 35), (0, 35)],
            ],
            result_right=[
                [(3, None), (11, 0, 11), (0, 11)],
                [(6, None), (8, 12, 20), (0, 20)],
                [(14, 21, 35), (0, 35)],
            ],
        )

    def test_calc_translate_word_2(self):
        self.check(
            text="It's out of control!\nYou've got to ",
            mode="space",
            width=14,
            result_left=[[(11, 0, 11), (0, 11)], [(8, 12, 20), (0, 20)], [(14, 21, 35), (0, 35)]],
            result_center=[
                [(2, None), (11, 0, 11), (0, 11)],
                [(3, None), (8, 12, 20), (0, 20)],
                [(14, 21, 35), (0, 35)],
            ],
            result_right=[
                [(3, None), (11, 0, 11), (0, 11)],
                [(6, None), (8, 12, 20), (0, 20)],
                [(14, 21, 35), (0, 35)],
            ],
        )

    def test_calc_translate_word_3(self):
        # As bytes: b'\xe6\x9b\xbf\xe6\xb4\xbc\n\xe6\xb8\x8e\xe6\xba\x8f\xe6\xbd\xba'
        # Decoded as UTF-8: "替洼\n渎溏潺"
        self.check(
            text=b"\xe6\x9b\xbf\xe6\xb4\xbc\n\xe6\xb8\x8e\xe6\xba\x8f\xe6\xbd\xba",
            width=10,
            mode="space",
            result_left=[[(4, 0, 6), (0, 6)], [(6, 7, 16), (0, 16)]],
            result_center=[[(3, None), (4, 0, 6), (0, 6)], [(2, None), (6, 7, 16), (0, 16)]],
            result_right=[[(6, None), (4, 0, 6), (0, 6)], [(4, None), (6, 7, 16), (0, 16)]],
        )

    def test_calc_translate_word_3_decoded(self):
        # As bytes: b'\xe6\x9b\xbf\xe6\xb4\xbc\n\xe6\xb8\x8e\xe6\xba\x8f\xe6\xbd\xba'
        # Decoded as UTF-8: "替洼\n渎溏潺"
        self.check(
            text="替洼\n渎溏潺",
            width=10,
            mode="space",
            result_left=[[(4, 0, 2), (0, 2)], [(6, 3, 6), (0, 6)]],
            result_center=[[(3, None), (4, 0, 2), (0, 2)], [(2, None), (6, 3, 6), (0, 6)]],
            result_right=[[(6, None), (4, 0, 2), (0, 2)], [(4, None), (6, 3, 6), (0, 6)]],
        )

    def test_calc_translate_word_4(self):
        self.check(
            text=" Die Gedank",
            width=3,
            mode="space",
            result_left=[[(0, 0)], [(3, 1, 4), (0, 4)], [(3, 5, 8)], [(3, 8, 11), (0, 11)]],
            result_center=[[(2, None), (0, 0)], [(3, 1, 4), (0, 4)], [(3, 5, 8)], [(3, 8, 11), (0, 11)]],
            result_right=[[(3, None), (0, 0)], [(3, 1, 4), (0, 4)], [(3, 5, 8)], [(3, 8, 11), (0, 11)]],
        )

    def test_calc_translate_word_5(self):
        self.check(
            text=" Word.",
            width=3,
            mode="space",
            result_left=[[(3, 0, 3)], [(3, 3, 6), (0, 6)]],
            result_center=[[(3, 0, 3)], [(3, 3, 6), (0, 6)]],
            result_right=[[(3, 0, 3)], [(3, 3, 6), (0, 6)]],
        )

    def test_calc_translate_clip(self):
        self.check(
            text="It's out of control!\nYou've got to\n\nturn it off!!!",
            mode="clip",
            width=14,
            result_left=[
                [(20, 0, 20), (0, 20)],
                [(13, 21, 34), (0, 34)],
                [(0, 35)],
                [(14, 36, 50), (0, 50)],
            ],
            result_center=[
                [(-3, None), (20, 0, 20), (0, 20)],
                [(1, None), (13, 21, 34), (0, 34)],
                [(7, None), (0, 35)],
                [(14, 36, 50), (0, 50)],
            ],
            result_right=[
                [(-6, None), (20, 0, 20), (0, 20)],
                [(1, None), (13, 21, 34), (0, 34)],
                [(14, None), (0, 35)],
                [(14, 36, 50), (0, 50)],
            ],
        )

    def test_calc_translate_clip_2(self):
        self.check(
            text="Hello!\nto\nWorld!",
            mode="clip",
            width=5,  # line width (of first and last lines) minus one
            result_left=[
                [(6, 0, 6), (0, 6)],
                [(2, 7, 9), (0, 9)],
                [(6, 10, 16), (0, 16)],
            ],
            result_center=[
                [(6, 0, 6), (0, 6)],
                [(2, None), (2, 7, 9), (0, 9)],
                [(6, 10, 16), (0, 16)],
            ],
            result_right=[
                [(-1, None), (6, 0, 6), (0, 6)],
                [(3, None), (2, 7, 9), (0, 9)],
                [(-1, None), (6, 10, 16), (0, 16)],
            ],
        )

    def test_calc_translate_cant_display(self):
        self.check(
            text="Hello颖",
            mode="space",
            width=1,
            result_left=[[]],
            result_center=[[]],
            result_right=[[]],
        )


class CalcPosTest(unittest.TestCase):
    def setUp(self):
        self.text = "A" * 27
        self.trans = [[(2, None), (7, 0, 7), (0, 7)], [(13, 8, 21), (0, 21)], [(3, None), (5, 22, 27), (0, 27)]]
        self.mytests = [
            (1, 0, 0),
            (2, 0, 0),
            (11, 0, 7),
            (-3, 1, 8),
            (-2, 1, 8),
            (1, 1, 9),
            (31, 1, 21),
            (1, 2, 22),
            (11, 2, 27),
        ]

    def tests(self):
        for x, y, expected in self.mytests:
            got = text_layout.calc_pos(self.text, self.trans, x, y)
            self.assertEqual(expected, got, f"{x, y!r} got:{got!r} expected:{expected!r}")


class Pos2CoordsTest(unittest.TestCase):
    pos_list = [5, 9, 20, 26]
    text = "1234567890" * 3
    mytests = [
        ([[(15, 0, 15)], [(15, 15, 30), (0, 30)]], [(5, 0), (9, 0), (5, 1), (11, 1)]),
        ([[(9, 0, 9)], [(12, 9, 21)], [(9, 21, 30), (0, 30)]], [(5, 0), (0, 1), (11, 1), (5, 2)]),
        ([[(2, None), (15, 0, 15)], [(2, None), (15, 15, 30), (0, 30)]], [(7, 0), (11, 0), (7, 1), (13, 1)]),
        ([[(3, 6, 9), (0, 9)], [(5, 20, 25), (0, 25)]], [(0, 0), (3, 0), (0, 1), (5, 1)]),
        ([[(10, 0, 10), (0, 10)]], [(5, 0), (9, 0), (10, 0), (10, 0)]),
    ]

    def test(self):
        for t, answer in self.mytests:
            for pos, a in zip(self.pos_list, answer):
                r = text_layout.calc_coords(self.text, t, pos)
                self.assertEqual(a, r, f"{t!r} got: {r!r} expected: {a!r}")


class TestEllipsis(unittest.TestCase):
    def test_ellipsis_encoding_support(self):
        widget = urwid.Text("Test label", wrap=urwid.WrapMode.ELLIPSIS)

        with self.subTest("Unicode"), set_temporary_encoding("utf-8"):
            widget._invalidate()
            canvas = widget.render((5,))
            self.assertEqual("Test…", str(canvas))

        with self.subTest("ascii"), set_temporary_encoding("ascii"):
            widget._invalidate()
            canvas = widget.render((5,))
            self.assertEqual("Te...", str(canvas))

        with self.subTest("ascii not fit"), set_temporary_encoding("ascii"):
            widget._invalidate()
            canvas = widget.render((3,))
            self.assertEqual("T..", str(canvas))

        with self.subTest("ascii nothing fit"), set_temporary_encoding("ascii"):
            widget._invalidate()
            canvas = widget.render((1,))
            self.assertEqual("T", str(canvas))

    def test_ellipsis_multichar_alignment(self):
        """A multi-character ellipsis has to be counted at its real width.

        The trimmed text plus the ellipsis fills all the available columns, so
        `align` has nothing left to distribute and every alignment renders alike.
        """
        for encoding, expected in (("utf-8", "Test…"), ("ascii", "Te...")):
            for align in (urwid.Align.LEFT, urwid.Align.CENTER, urwid.Align.RIGHT):
                with self.subTest(encoding=encoding, align=align), set_temporary_encoding(encoding):
                    widget = urwid.Text("Test label", align=align, wrap=urwid.WrapMode.ELLIPSIS)
                    self.assertEqual(expected, str(widget.render((5,))))

    def test_ellipsis_line_declares_available_columns(self):
        """A trimmed line and its ellipsis together declare exactly `width` columns."""
        layout = urwid.StandardTextLayout()
        for encoding in ("utf-8", "ascii"):
            for width in range(3, 10):
                with self.subTest(encoding=encoding, width=width), set_temporary_encoding(encoding):
                    segments = layout.layout("Test label", width, urwid.Align.LEFT, urwid.WrapMode.ELLIPSIS)
                    self.assertEqual(width, sum(segment[0] for segment in segments[0]))


class NumericLayout(urwid.TextLayout):
    """
    TextLayout class for bottom-right aligned numbers
    """

    def layout(
        self,
        text: str | bytes,
        width: int,
        align: Literal["left", "center", "right"] | urwid.Align,
        wrap: Literal["any", "space", "clip", "ellipsis"] | urwid.WrapMode,
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]]:
        """
        Return layout structure for right justified numbers.
        """
        lt = len(text)
        r = lt % width  # remaining segment not full width wide
        if r:
            return [
                [(width - r, None), (r, 0, r)],  # right-align the remaining segment on 1st line
                *([(width, x, x + width)] for x in range(r, lt, width)),  # fill the rest of the lines
            ]

        return [[(width, x, x + width)] for x in range(0, lt, width)]


class TestTextLayoutNoPack(unittest.TestCase):
    def test(self):
        """Text widget pack should work also with layout not supporting `pack` method."""
        widget = urwid.Text("123", layout=NumericLayout())
        self.assertEqual((3, 1), widget.pack((3,)))


class SupportsModeTest(unittest.TestCase):
    def test_base_class_supports_everything(self):
        base = text_layout.TextLayout()
        self.assertTrue(base.supports_align_mode("bogus"))
        self.assertTrue(base.supports_wrap_mode("bogus"))

    def test_base_class_layout_not_implemented(self):
        base = text_layout.TextLayout()
        self.assertRaises(NotImplementedError, base.layout, "text", 10, "left", "space")

    def test_standard_layout_align_modes(self):
        layout = text_layout.default_layout
        for align in ("left", "center", "right"):
            self.assertTrue(layout.supports_align_mode(align))
        self.assertFalse(layout.supports_align_mode("bogus"))

    def test_standard_layout_wrap_modes(self):
        layout = text_layout.default_layout
        for wrap in ("any", "space", "clip", "ellipsis"):
            self.assertTrue(layout.supports_wrap_mode(wrap))
        self.assertFalse(layout.supports_wrap_mode("bogus"))


class PackTest(unittest.TestCase):
    def test_empty_layout_raises(self):
        self.assertRaises(ValueError, text_layout.default_layout.pack, 10, [])

    def test_maxcol_returned_when_line_reaches_it(self):
        segs = [[(5, 0, 5)], [(20, 0, 20)]]
        self.assertEqual(10, text_layout.default_layout.pack(10, segs))

    def test_max_line_width_returned_otherwise(self):
        segs = [[(3, 0, 3)], [(7, 0, 7)]]
        self.assertEqual(7, text_layout.default_layout.pack(10, segs))


class AlignLayoutTest(unittest.TestCase):
    def test_invalid_align_raises(self):
        self.assertRaises(
            ValueError,
            text_layout.default_layout.align_layout,
            "abcde",
            10,
            [[(5, 0, 5)]],
            "space",
            "bogus",
        )

    def test_invalid_wrap_mode_raises(self):
        self.assertRaises(
            ValueError,
            text_layout.default_layout.calculate_text_segments,
            "abcdefghij",
            3,
            "bogus",
        )


class WideCharWordWrapTest(unittest.TestCase):
    """Word-wrap (mode "space") breaking right after a wide character."""

    def test_wrap_after_wide_char(self):
        with set_temporary_encoding("euc-jp"):
            for text in (
                b"\xa1\xa1\xa1\xa1\xa1\xa1abcdefgh",
                b"ab\xa1\xa1\xa1\xa1cdefgh",
                b"\xa1\xa1bcdefghij",
            ):
                for width in range(2, 8):
                    with self.subTest(text=text, width=width):
                        # must not raise, just exercise the wide-char break path
                        text_layout.default_layout.calculate_text_segments(text, width, "space")


class ZwjSequenceTest(unittest.TestCase):
    """Emoji ZWJ sequences are one grapheme: no layout offset may point inside one."""

    def test_wrap_never_splits_sequence(self):
        for wrap in ("any", "space"):
            with self.subTest(wrap=wrap):
                self.assertEqual(
                    ["👩‍💻👩‍💻 ", "👩‍💻   "],
                    [row.decode() for row in urwid.Text("👩‍💻👩‍💻👩‍💻", wrap=wrap).render((5,)).text],
                )

    def test_trim_inside_sequence_pads_at_its_start(self):
        text = "ab 👨‍👩‍👧👨‍👩‍👧"
        line = text_layout.default_layout.layout(text, 100, "left", "clip")[0]
        # column 4 is the right half of the first family emoji, which starts at offset 3
        self.assertEqual([(1, 3), (2, 8, 13)], text_layout.trim_line(line, text, 4, 7))

    def test_trim_inside_sequence_renders_space(self):
        text = "👨‍👩‍👧👨‍👩‍👧"
        line = text_layout.default_layout.layout(text, 100, "left", "clip")[0]
        trimmed = text_layout.trim_line(line, text, 1, 4)
        self.assertEqual(" 👨‍👩‍👧", canvas.apply_text_layout(text, [], [trimmed], 3).text[0].decode())


class LineWidthTest(unittest.TestCase):
    def test_ignores_leading_shift(self):
        self.assertEqual(5, text_layout.line_width([(3, None), (5, 0, 5)]))
        self.assertEqual(5, text_layout.line_width([(5, 0, 5)]))


class ShiftLineTest(unittest.TestCase):
    def test_shift_no_existing_shift(self):
        self.assertEqual([(3, None), (5, 0, 5)], text_layout.shift_line([(5, 0, 5)], 3))

    def test_shift_combines_with_existing_shift(self):
        self.assertEqual([(5, None), (5, 0, 5)], text_layout.shift_line([(3, None), (5, 0, 5)], 2))

    def test_shift_removes_existing_shift_when_zero(self):
        self.assertEqual([(5, 0, 5)], text_layout.shift_line([(3, None), (5, 0, 5)], -3))

    def test_shift_by_zero_is_noop(self):
        self.assertEqual([(5, 0, 5)], text_layout.shift_line([(5, 0, 5)], 0))

    def test_non_int_amount_raises(self):
        self.assertRaises(TypeError, text_layout.shift_line, [(5, 0, 5)], "x")


class LayoutSegmentInitTest(unittest.TestCase):
    def test_not_a_tuple_raises_type_error(self):
        self.assertRaises(TypeError, text_layout.LayoutSegment, 0)

    def test_three_tuple_sc_not_int_raises_type_error(self):
        self.assertRaises(TypeError, text_layout.LayoutSegment, ("x", 0, 5))

    def test_three_tuple_offs_not_int_raises_type_error(self):
        self.assertRaises(TypeError, text_layout.LayoutSegment, (5, "a", 5))

    def test_three_tuple_sc_not_positive_raises_value_error(self):
        self.assertRaises(ValueError, text_layout.LayoutSegment, (0, 0, 5))

    def test_three_tuple_text_wrong_type_raises_type_error(self):
        self.assertRaises(TypeError, text_layout.LayoutSegment, (5, 0, 3.5))

    def test_two_tuple_sc_not_int_raises_type_error(self):
        self.assertRaises(TypeError, text_layout.LayoutSegment, ("x", 0))

    def test_two_tuple_negative_sc_with_offs_raises_value_error(self):
        self.assertRaises(ValueError, text_layout.LayoutSegment, (-1, 0))

    def test_two_tuple_offs_not_int_raises_type_error(self):
        self.assertRaises(TypeError, text_layout.LayoutSegment, (5, "x"))

    def test_wrong_length_raises_value_error(self):
        self.assertRaises(ValueError, text_layout.LayoutSegment, (1, 2, 3, 4))


class LayoutSegmentSubsegTest(unittest.TestCase):
    def test_start_past_end_returns_empty(self):
        seg = text_layout.LayoutSegment((5, 0, 5))
        self.assertEqual([], seg.subseg("abcde", 5, 3))
        self.assertEqual([], seg.subseg("abcde", 5, 5))

    def test_offs_none_with_end_raises_value_error(self):
        # Defensive guard: normal construction cannot leave offs None while end is set,
        # so exercise it directly via the __slots__ attribute.
        seg = text_layout.LayoutSegment((5, 0, 5))
        seg.offs = None
        self.assertRaises(ValueError, seg.subseg, "abcde", 0, 3)


class CalcLiteralLinePosTest(unittest.TestCase):
    text = "A" * 27
    line = [(2, None), (7, 0, 7), (0, 7)]

    def test_left(self):
        self.assertEqual(0, text_layout._calc_literal_line_pos(self.text, self.line, "left"))

    def test_left_no_offset_found(self):
        self.assertIsNone(text_layout._calc_literal_line_pos(self.text, [(5, None)], "left"))

    def test_right(self):
        self.assertEqual(7, text_layout._calc_literal_line_pos(self.text, self.line, "right"))

    def test_right_no_offset_found(self):
        self.assertIsNone(text_layout._calc_literal_line_pos(self.text, [(5, None)], "right"))

    def test_right_without_end(self):
        self.assertEqual(2, text_layout._calc_literal_line_pos(self.text, [(3, 2)], "right"))

    def test_right_with_end(self):
        self.assertEqual(2, text_layout._calc_literal_line_pos(self.text, [(3, 0, 3)], "right"))

    def test_invalid_pref_col_raises(self):
        self.assertRaises(ValueError, text_layout._calc_literal_line_pos, self.text, self.line, "bogus")


class CalcLinePosTest(unittest.TestCase):
    def test_left_dispatches_to_literal(self):
        line = [(2, None), (7, 0, 7), (0, 7)]
        self.assertEqual(0, text_layout.calc_line_pos("A" * 27, line, "left"))

    def test_invalid_pref_col_raises_type_error(self):
        line = [(2, None), (7, 0, 7), (0, 7)]
        self.assertRaises(TypeError, text_layout.calc_line_pos, "A" * 27, line, "bogus")

    def test_numeric_beyond_line_returns_last_int_position(self):
        self.assertEqual(21, text_layout.calc_line_pos("A" * 27, [(13, 8, 21), (0, 21)], 100))

    def test_numeric_beyond_single_segment_returns_last_segment_position(self):
        self.assertEqual(4, text_layout.calc_line_pos("abcde", [(5, 0, 5)], 100))


class CalcPosTest2(unittest.TestCase):
    def test_row_out_of_range_raises(self):
        text = "A" * 27
        trans = [[(2, None), (7, 0, 7), (0, 7)], [(13, 8, 21), (0, 21)]]
        self.assertRaises(ValueError, text_layout.calc_pos, text, trans, "left", 10)

    def test_falls_back_to_neighboring_rows(self):
        text = "A" * 27
        layout = [[(5, None)], [(7, 0, 7), (0, 7)]]
        self.assertEqual(0, text_layout.calc_pos(text, layout, "left", 0))

    def test_falls_back_searching_both_directions(self):
        text = "A" * 27
        layout = [[(5, None)], [(5, None)], [(7, 0, 7), (0, 7)]]
        self.assertEqual(0, text_layout.calc_pos(text, layout, "left", 1))

    def test_no_match_in_any_row_returns_zero(self):
        text = "A" * 27
        layout = [[(5, None)]] * 6
        self.assertEqual(0, text_layout.calc_pos(text, layout, "left", 2))

    def test_falls_back_with_unequal_row_counts(self):
        text = "A" * 40
        layout = [[(5, None)]] * 5 + [[(7, 0, 7), (0, 7)]]
        self.assertEqual(0, text_layout.calc_pos(text, layout, "left", 2))

    def test_falls_back_matching_row_above(self):
        text = "A" * 27
        pad = [(5, None)]
        row_with_offs = [(7, 0, 7), (0, 7)]
        layout = [pad, pad, row_with_offs, pad, pad]
        self.assertEqual(0, text_layout.calc_pos(text, layout, "left", 3))


class TrimLineTest(unittest.TestCase):
    def test_multi_segment_line_not_widened(self):
        # regression test: trim_line must stop appending whole segments once
        # their cumulative width reaches `end`, even across more than one
        # full segment (previously `x` was not advanced for segments taken
        # as-is, so more segments than requested were appended).
        segs = [(3, 0, 3), (3, 3, 6), (4, 6, 10)]
        self.assertEqual([(3, 0, 3)], text_layout.trim_line(segs, "abcdefghij", 0, 3))


class CalcCoordsTest(unittest.TestCase):
    def test_empty_layout_returns_origin(self):
        self.assertEqual((0, 0), text_layout.calc_coords("A" * 27, [], 5))

    def test_no_exact_match_falls_back_to_closest(self):
        self.assertEqual((0, 0), text_layout.calc_coords("A" * 27, [[(5, None)]], 3))

    def test_distance_based_closest_match(self):
        self.assertEqual((2, 0), text_layout.calc_coords("A" * 27, [[(2, None), (3, 5, 8)]], 2))


class TestTextTranslationCacheThreads(unittest.TestCase):
    """The translation cache of one Text widget read and refilled from several threads at once.

    Buttons share the class-level ``button_left``/``button_right`` Text widgets, so two threads laying out
    buttons hit the same cache; each reader has to get the translation for the width it asked for.
    """

    @unittest.skipIf(
        sys.implementation.name == "graalpy",
        "under coverage tracing GraalPy needs longer than the join timeout for the forced thread switching",
    )
    def test_concurrent_widths(self):
        # The race window is a few bytecodes wide; the default 5 ms switch interval lets a whole run finish
        # inside one interval, so the threads have to be forced to interleave.
        self.addCleanup(sys.setswitchinterval, sys.getswitchinterval())
        sys.setswitchinterval(1e-6)

        widget = urwid.Text("The quick brown fox jumps over the lazy dog, again and again and again.")
        widths = (12, 12, 20, 20, 33, 33)
        expected = {
            width: text_layout.default_layout.layout(widget.text, width, widget.align, widget.wrap) for width in widths
        }
        errors: list[BaseException] = []
        start = threading.Barrier(len(widths), timeout=30)

        def worker(width: int) -> None:
            start.wait()
            for _ in range(20_000):
                try:
                    translation = widget.get_line_translation(width)
                except Exception as exc:  # noqa: BLE001  # collected for the assertion on the test thread
                    errors.append(exc)
                    return
                if translation != expected[width]:
                    errors.append(AssertionError(f"translation for width {width} is not the one laid out for it"))
                    return

        threads = [threading.Thread(target=worker, args=(width,)) for width in widths]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
            self.assertFalse(thread.is_alive(), "worker thread did not finish")
        self.assertFalse(errors, errors)


class TabStopTest(unittest.TestCase):
    """Tab characters advance to word-processor style tab stops counted in rendered screen columns."""

    def render(self, text: str, width: int, **kwargs) -> list[str]:
        return [row.decode() for row in urwid.Text(text, **kwargs).render((width,)).text]

    def test_default_stops_every_8_columns(self):
        self.assertEqual(["1       2       3   "], self.render("1\t2\t3", 20))

    def test_stop_counts_rendered_width_of_wide_characters(self):
        # "中文" is 2 characters, but 4 screen columns
        self.assertEqual(["中文    x  "], self.render("中文\tx", 11))

    def test_stop_counts_zwj_sequence_as_one_wide_grapheme(self):
        # 3 code points joined by ZWJ, 2 screen columns
        self.assertEqual(["👩‍💻      x   "], self.render("👩‍💻\tx", 12))

    def test_zwj_sequence_is_not_split_by_wrap_after_tab(self):
        self.assertEqual(
            [[(1, 0, 1), (7, 1, b"       "), (2, 2, 7)], [(3, 7, 13), (0, 13)]],
            text_layout.default_layout.layout("a\t👨‍👩‍👧👨‍👩‍👧b", 10, "left", "space"),
        )
        self.assertEqual(["a       👨‍👩‍👧 ", "👨‍👩‍👧b        "], self.render("a\t👨‍👩‍👧👨‍👩‍👧b", 11, wrap="any"))

    def test_ellipsis_after_tab_keeps_zwj_sequence_whole(self):
        self.assertEqual(["a       👩‍💻…"], self.render("a\t👩‍💻👩‍💻", 11, wrap="ellipsis"))

    def test_tab_on_stop_advances_to_the_next_one(self):
        self.assertEqual(["12345678        y"], self.render("12345678\ty", 17))

    def test_explicit_stops_then_interval(self):
        layout = text_layout.StandardTextLayout(tab_stops=(10, 3), tab_stop_every=4)
        self.assertEqual(
            ["a  b      c d     "],
            self.render("a\tb\tc\td", 18, layout=layout),
        )

    def test_next_tab_stop(self):
        layout = text_layout.StandardTextLayout(tab_stops=(4, 10))
        self.assertEqual([4, 4, 10, 16, 16], [layout.next_tab_stop(col) for col in (0, 3, 4, 10, 15)])

    def test_zero_tab_width(self):
        layout = text_layout.StandardTextLayout(tab_stop_every=0)
        self.assertEqual(
            [[(1, 0, 1), (0, 1), (1, 2, 3), (0, 3)]],
            layout.layout("a\tb", 10, "left", "space"),
        )
        self.assertEqual(["ab        "], self.render("a\tb", 10, layout=layout))
        self.assertEqual((2, 1), urwid.Text("a\tb", layout=layout).pack())

    def test_zero_tab_width_after_last_explicit_stop(self):
        layout = text_layout.StandardTextLayout(tab_stops=(4,), tab_stop_every=0)
        self.assertEqual([4, 4], [layout.next_tab_stop(col) for col in (0, 4)])
        self.assertEqual(["a   bc    "], self.render("a\tb\tc", 10, layout=layout))
        self.assertEqual((6, 1), urwid.Text("a\tb\tc", layout=layout).pack())

    def test_zero_tab_width_at_line_end(self):
        layout = text_layout.StandardTextLayout(tab_stop_every=0)
        for wrap in ("any", "space"):
            with self.subTest(wrap=wrap):
                self.assertEqual(
                    [[(4, 0, 4), (0, 4)], [(1, 5, 6), (0, 6)]],
                    layout.layout("abcd\te", 4, "left", wrap),
                )
        self.assertEqual([[(0, 0), (0, 1)]], layout.layout("\t", 0, "left", "any"))

    def test_zero_tab_width_trimmed(self):
        layout = text_layout.StandardTextLayout(tab_stop_every=0)
        self.assertEqual(["abc…"], self.render("a\tbcdef", 4, wrap="ellipsis", layout=layout))
        self.assertEqual(["ab  "], self.render("a\tb", 4, wrap="clip", layout=layout))

    def test_invalid_stops_raise(self):
        self.assertRaises(ValueError, text_layout.StandardTextLayout, tab_stop_every=-1)
        self.assertRaises(ValueError, text_layout.StandardTextLayout, tab_stops=(0, 4))

    def test_tab_is_one_segment_rendered_as_spaces(self):
        self.assertEqual(
            [[(2, 0, 2), (6, 2, b"      "), (1, 3, 4), (0, 4)]],
            text_layout.default_layout.layout("ab\tc", 20, "left", "space"),
        )

    def test_bytes_text(self):
        self.assertEqual(
            [[(2, 0, 2), (6, 2, b"      "), (1, 3, 4), (0, 4)]],
            text_layout.default_layout.layout(b"ab\tc", 20, "left", "any"),
        )

    def test_space_wrap_moves_word_after_tab_to_next_line(self):
        self.assertEqual(
            ["aaa         ", "bbbbbbb ccc ", "ddd         "],
            self.render("aaa\tbbbbbbb\tccc ddd", 12, wrap="space"),
        )

    def test_stops_restart_on_each_display_line(self):
        self.assertEqual(["aaaaa   ", "bbb     ", "c       "], self.render("aaaaa bbb\tc", 8))

    def test_space_wrap_drops_tab_at_line_end(self):
        self.assertEqual(
            [[(8, 0, 8), (0, 8)], [(1, 9, 10), (0, 10)]],
            text_layout.default_layout.layout("12345678\tx", 8, "left", "space"),
        )

    def test_tab_is_cut_at_line_end(self):
        self.assertEqual(
            [[(3, 0, 3), (3, 3, b"   ")], [(1, 4, 5), (0, 5)]],
            text_layout.default_layout.layout("abc\tx", 6, "left", "space"),
        )

    def test_any_wrap(self):
        self.assertEqual(
            ["aaa     bbbb", "bbb     ccc ", "ddd         "],
            self.render("aaa\tbbbbbbb\tccc ddd", 12, wrap="any"),
        )

    def test_any_wrap_moves_tab_at_line_end_to_next_line(self):
        self.assertEqual(
            [[(8, 0, 8)], [(8, 8, b"        ")], [(1, 9, 10), (0, 10)]],
            text_layout.default_layout.layout("12345678\tx", 8, "left", "any"),
        )

    def test_word_not_fitting_after_tab_moves_to_next_line(self):
        layout = text_layout.StandardTextLayout(tab_stop_every=4)
        self.assertEqual(["        ", "abcdefgh"], self.render("\tabcdefgh", 8, layout=layout))

    def test_word_longer_than_line_is_char_wrapped(self):
        self.assertEqual(["x          ", "abcdefghijk", "lmnop      "], self.render("x\tabcdefghijklmnop", 11))

    def test_clip(self):
        self.assertEqual(["aaa   "], self.render("aaa\tbbb", 6, wrap="clip"))

    def test_ellipsis_cuts_text_after_tab(self):
        self.assertEqual(["aaa     bbb…"], self.render("aaa\tbbbbbbbbbbb\tccc", 12, wrap="ellipsis"))

    def test_ellipsis_cuts_tab(self):
        self.assertEqual(["abc   …"], self.render("abc\tdef", 7, wrap="ellipsis"))

    def test_ellipsis_not_needed(self):
        self.assertEqual(["abc     d  "], self.render("abc\td", 11, wrap="ellipsis"))

    def test_ellipsis_at_tab_stop(self):
        self.assertEqual(["abcdef…"], self.render("abcdef\tx", 7, wrap="ellipsis"))

    def test_ellipsis_with_wide_char_at_limit(self):
        self.assertEqual(["a       … "], self.render("a\t中中", 10, wrap="ellipsis"))

    def test_zero_width_chunk_between_tabs(self):
        self.assertEqual(["a               b"], self.render("a\t\u200b\tb", 17))
        self.assertEqual(["a               b"], self.render("a\t\u200b\tb", 17, wrap="clip"))

    def test_space_wrap_at_space_after_tab(self):
        self.assertEqual(["aaa     bb", "cc        "], self.render("aaa\tbb cc", 10))

    def test_space_wrap_right_after_tab_drops_space(self):
        self.assertEqual(["a       ", "bbb     "], self.render("a\t bbb", 8))

    def test_space_wrap_before_wide_char(self):
        self.assertEqual(["a       b ", "中        "], self.render("a\tb中", 10))

    def test_space_wrap_after_wide_char(self):
        self.assertEqual(["a       中 ", "bc         "], self.render("a\t中bc", 11))

    def test_right_alignment_shifts_the_whole_line(self):
        self.assertEqual(["   a       b"], self.render("a\tb", 12, align="right"))

    def test_zero_width_raises_can_not_display(self):
        self.assertEqual([[]], text_layout.default_layout.layout("\ta", 0, "left", "any"))

    def test_wide_char_does_not_fit_raises_can_not_display(self):
        self.assertEqual([[]], text_layout.default_layout.layout("\t中", 1, "left", "space"))

    def test_unsupported_wrap_raises(self):
        self.assertRaises(ValueError, text_layout.default_layout._wrap_tabbed_line, "\t", 0, 1, 8, "clip")

    def test_pack_counts_tabs(self):
        text = urwid.Text("ab\tc")
        self.assertEqual((9, 1), text.pack())
        self.assertEqual(["ab      c"], [row.decode() for row in text.render(()).text])

    def test_pack_counts_tabs_with_alignment(self):
        for align in ("left", "center", "right"):
            with self.subTest(align=align):
                self.assertEqual((9, 1), urwid.Text("ab\tc", align=align).pack())

    def test_pack_reaches_far_tab_stop(self):
        layout = text_layout.StandardTextLayout(tab_stops=(40,))
        self.assertEqual((41, 1), urwid.Text("x\ty", layout=layout).pack())

    def test_pack_multiline_with_emoji_and_tab(self):
        self.assertEqual((9, 2), urwid.Text("👩‍💻\tx\n中文").pack())

    def test_pack_layout_without_pack_method(self):
        class NoPackLayout(urwid.TextLayout):
            def layout(self, text, width, align, wrap):
                return [[(len(text), 0, len(text))]]

        self.assertEqual((4, 1), urwid.Text("abcd", layout=NoPackLayout()).pack())

    def test_pack_layout_wider_than_text(self):
        """A custom layout wider than the text makes pack() retry at a wider maxcol."""

        class DoubleWidthLayout(urwid.TextLayout):
            """Lay out the text on one line of twice its length."""

            def layout(self, text, width, align, wrap):
                return [[(2 * len(text), 0, len(text))]]

            def pack(self, maxcol, layout):
                """Return the line width, capped at maxcol."""
                return min(maxcol, text_layout.line_width(layout[0]))

        self.assertEqual((8, 1), urwid.Text("abcd", layout=DoubleWidthLayout()).pack())

    def test_edit_cursor_steps_over_tab(self):
        edit = urwid.Edit("", "ab\tcd")
        coords = []
        for pos in range(6):
            edit.set_edit_pos(pos)
            coords.append(edit.get_cursor_coords((20,)))
        self.assertEqual([(0, 0), (1, 0), (2, 0), (8, 0), (9, 0), (10, 0)], coords)

    def test_edit_cursor_after_zwj_sequence_and_tab(self):
        edit = urwid.Edit("", "👩‍💻\tx")
        edit.set_edit_pos(len("👩‍💻\t"))
        self.assertEqual((8, 0), edit.get_cursor_coords((20,)))
        edit.set_edit_pos(len("👩‍💻"))
        self.assertEqual((2, 0), edit.get_cursor_coords((20,)))

    def test_edit_click_inside_tab(self):
        edit = urwid.Edit("", "ab\tcd")
        edit.move_cursor_to_coords((20,), 4, 0)
        self.assertEqual(2, edit.edit_pos)
        edit.move_cursor_to_coords((20,), 7, 0)
        self.assertEqual(3, edit.edit_pos)


class _CountingText(str):
    """A text that adds the length of every range its ``find`` scans to ``scanned``."""

    __slots__ = ()
    scanned = 0

    def find(self, sub, start=0, end=None):
        """Count the scanned range, then search it."""
        _CountingText.scanned += (len(self) if end is None else end) - start
        return super().find(sub, start, end)


class _CountingBytes(bytes):
    """A byte string that adds the length of every range its ``find`` scans to ``_CountingText.scanned``."""

    __slots__ = ()

    def find(self, sub, start=0, end=None):
        """Count the scanned range, then search it."""
        _CountingText.scanned += (len(self) if end is None else end) - start
        return super().find(sub, start, end)


class LongParagraphWorkTest(unittest.TestCase):
    """Laying out a paragraph scans each character a bounded number of times, whatever its length."""

    def count_processed(self, text: str | bytes, wrap: Literal["any", "space"]) -> int:
        """Return how many characters the layout of text hands to the scanning and measuring functions."""
        real_iter_graphemes = wcwidth.iter_graphemes
        real_width = wcwidth.width

        def iter_graphemes(unistr, start=0, end=None):
            if start == 0 and end is None:
                # the C segmenter prepares the whole string before it yields the first cluster
                _CountingText.scanned += len(unistr)
            for grapheme in real_iter_graphemes(unistr, start, end):
                _CountingText.scanned += len(grapheme)
                yield grapheme

        def width(unistr, **kwargs):
            _CountingText.scanned += len(unistr)
            return real_width(unistr, **kwargs)

        _CountingText.scanned = 0
        counting = _CountingText(text) if isinstance(text, str) else _CountingBytes(text)
        with unittest.mock.patch.multiple(wcwidth, iter_graphemes=iter_graphemes, width=width):
            text_layout.default_layout.calculate_text_segments(counting, 20, wrap)
        return _CountingText.scanned

    def assert_linear(self, make_text: Callable[[int], str | bytes]) -> None:
        """Assert that four times the text costs at most five times the work, for both wrap modes."""
        for wrap in ("any", "space"):
            with self.subTest(text=make_text(1), wrap=wrap):
                self.assertLess(
                    self.count_processed(make_text(4000), wrap), 5 * self.count_processed(make_text(1000), wrap)
                )

    def test_unbroken_paragraph(self):
        """A paragraph without spaces, also one holding a tab, costs work linear in its length."""
        self.assert_linear(lambda n: "x" * n)
        self.assert_linear(lambda n: "\u00e9" * n)
        self.assert_linear(lambda n: "x" * n + "\t" + "x" * n)

    def test_unbroken_utf8_paragraph(self):
        """A UTF-8 byte string paragraph without spaces costs work linear in its length."""
        with set_temporary_encoding("utf-8"):
            self.assert_linear(lambda n: b"x" * n)
            self.assert_linear(lambda n: "\u00e9".encode() * n)


class ClusterStartingBeforeLineTest(unittest.TestCase):
    """A grapheme cluster made of a space and a combining character is broken at the space."""

    def capped_segments(self, text: str | bytes, width: int) -> list:
        """Return the space-wrapped segments of text, raising once the layout stops advancing."""
        calls = 0
        real_calc_text_pos = text_layout.calc_text_pos

        def calc_text_pos(*args):
            nonlocal calls
            calls += 1
            if calls > 100:
                raise RuntimeError("the layout does not advance")
            return real_calc_text_pos(*args)

        with unittest.mock.patch.object(text_layout, "calc_text_pos", calc_text_pos):
            return text_layout.default_layout.calculate_text_segments(text, width, "space")

    def test_combining_mark_after_space(self):
        """Wrapping after the space does not measure a range that ends before it starts."""
        text = " \u0301hhgb\u00e9abbd"
        segments = text_layout.default_layout.calculate_text_segments(text, 8, "space")
        self.assertEqual(len(text), segments[-1][-1][-1])

    def test_emoji_modifier_after_space_before_tab(self):
        """Wrapping a line holding a tab advances past the cluster instead of breaking at its space again."""
        text = " \U0001f3fbxx\t"
        self.assertEqual(len(text), self.capped_segments(text, 3)[-1][-1][-1])

    def test_vowel_sign_after_space_in_long_word(self):
        """Joining a broken word with the line before it happens only when the break moves past the space."""
        for text, width in (
            ("abc \u093fdefgh ijk", 2),
            ("abc \u093fdefgh ijk", 4),
            ("\u0917\u0bb7 \u093f\u0939\u0926\u0939\u0928", 3),
        ):
            for encoded in (text, text.encode()):
                with self.subTest(text=encoded, width=width), set_temporary_encoding("utf-8"):
                    self.assertEqual(len(encoded), self.capped_segments(encoded, width)[-1][-1][-1])
