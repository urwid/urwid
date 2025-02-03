from __future__ import annotations

import typing
import unittest

import urwid
from urwid import text_layout
from urwid.util import get_encoding, set_temporary_encoding

if typing.TYPE_CHECKING:
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
        self.st((6, 2, 8), t, 1, 6, [(1, 3), (4, 4, 8)])
        self.st((6, 2, 8), t, 0, 5, [(4, 2, 6), (1, 6)])
        self.st((6, 2, 8), t, 1, 5, [(1, 3), (2, 4, 6), (1, 6)])


class CalcTranslateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def check(self, text, mode, width, result_left, result_center, result_right) -> None:
        with self.subTest("left"):
            result = urwid.default_layout.layout(text, width, "left", mode)
            self.assertEqual(result_left, result)

        with self.subTest("center"):
            result = urwid.default_layout.layout(text, width, "center", mode)
            self.assertEqual(result_center, result)

        with self.subTest("right"):
            result = urwid.default_layout.layout(text, width, "right", mode)
            self.assertEqual(result_right, result)

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
